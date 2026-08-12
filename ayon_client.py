import os
import ayon_api
import logging

class AyonClient:
    def __init__(self, server_url=None, api_key=None):
        self.is_connected = False
        self.server_url = server_url
        self.log = logging.getLogger("AyonClient")
        if server_url and api_key:
            self.connect(server_url, api_key)

    def connect(self, server_url, api_key):
        self.server_url = server_url
        if not server_url or not api_key:
            self.is_connected = False
            return False
            
        try:
            os.environ["AYON_SERVER_URL"] = server_url
            os.environ["AYON_API_KEY"] = api_key
            
            # Test connection
            self.con = ayon_api.get_server_api_connection()
            self.is_connected = True
            self.log.info("Successfully connected to AYON")
            return True
        except Exception as e:
            self.log.error(f"Failed to connect to AYON: {e}")
            self.is_connected = False
            return False

    def get_projects(self):
        if not self.is_connected: return []
        try:
            return ayon_api.get_project_names()
        except Exception as e:
            self.log.error(f"Error fetching projects: {e}")
            return []

    def get_project_hierarchy(self, project_name):
        """Fetch all folders and tasks for a project and organize into a tree."""
        if not self.is_connected: return []
        
        try:
            # Get all folders
            folders = list(ayon_api.get_folders(
                project_name,
                fields=["id", "name", "path", "type", "label", "status", "parentId", "thumbnailId", "attrib"]
            ))
            
            # Get all tasks
            tasks = list(ayon_api.get_tasks(
                project_name,
                fields=["id", "name", "type", "label", "status", "folderId", "assignees", "thumbnailId"]
            ))
            
            # Organize into a map by ID for easy lookup
            folder_map = {str(f["id"]): {**f, "children": [], "tasks": []} for f in folders}
            
            # Add tasks to their folders
            for task in tasks:
                f_id = task.get("folderId")
                if f_id:
                    f_id_str = str(f_id)
                    if f_id_str in folder_map:
                        folder_map[f_id_str]["tasks"].append(task)
            
            # Build the tree
            root_folders = []
            for f_id, folder in folder_map.items():
                p_id = folder.get("parentId")
                if p_id:
                    p_id_str = str(p_id)
                    if p_id_str in folder_map:
                        folder_map[p_id_str]["children"].append(folder)
                    else:
                        root_folders.append(folder)
                else:
                    root_folders.append(folder)
            
            return root_folders
        except Exception as e:
            self.log.error(f"Error fetching hierarchy for project {project_name}: {e}")
            return []

    def get_last_versions(self, project_name, folder_ids):
        """Fetch all products for multiple folders and return a map: (folder_id, prod_name, prod_type) -> last_version."""
        if not self.is_connected or not folder_ids: return {}
        try:
            products = list(ayon_api.get_products(project_name, folder_ids=folder_ids))
            self.log.info(f"Found {len(products)} products in folders {folder_ids}")
            res = {}
            for prod in products:
                # Get last version
                last_v = ayon_api.get_last_version_by_product_id(project_name, prod["id"])
                v_num = last_v["version"] if last_v else 0
                f_id = str(prod["folderId"])
                p_name = prod["name"]
                p_type = prod.get("productType") or prod.get("type")
                
                self.log.info(f"AYON Product: {p_name} ({p_type}) in folder {f_id} -> v{v_num}")
                # Use string key to avoid PySide/Shiboken tuple conversion issues
                res[f"{f_id}|{p_name}|{p_type}"] = v_num
            return res
        except Exception as e:
            self.log.error(f"Error fetching versions for folders {folder_ids}: {e}")
            return {}

    def get_products_for_folder(self, project_name, folder_id):
        """Get all products and their latest versions for a folder."""
        if not self.is_connected: return []
        try:
            products = list(ayon_api.get_products(project_name, folder_ids=[folder_id]))
            res = []
            for prod in products:
                # Get last version
                last_v = ayon_api.get_last_version_by_product_id(project_name, prod["id"])
                v_num = last_v["version"] if last_v else 0
                p_name = prod["name"]
                p_type = prod.get("productType") or prod.get("type")
                
                prod_data = prod.get("data") or {}
                last_v_data = (last_v.get("data") or {}) if last_v else {}
                
                t_id = (
                    prod.get("taskId") or
                    prod_data.get("taskId") or
                    prod_data.get("task_id") or
                    (last_v.get("taskId") if last_v else None) or
                    last_v_data.get("taskId") or
                    last_v_data.get("task_id")
                )
                
                t_name = (
                    prod_data.get("task_name") or
                    prod_data.get("taskName") or
                    (prod_data.get("task", {}).get("name") if isinstance(prod_data.get("task"), dict) else None) or
                    last_v_data.get("task_name") or
                    last_v_data.get("taskName") or
                    (last_v_data.get("task", {}).get("name") if isinstance(last_v_data.get("task"), dict) else None)
                )
                
                res.append({
                    "id": str(prod["id"]),
                    "name": p_name,
                    "type": p_type,
                    "version": v_num,
                    "version_id": str(last_v["id"]) if last_v and last_v.get("id") else None,
                    "version_status": str(last_v.get("status")) if last_v and last_v.get("status") else "",
                    "task_id": str(t_id) if t_id else None,
                    "task_name": str(t_name) if t_name else None,
                })
            return res
        except Exception as e:
            self.log.error(f"Error fetching products for folder {folder_id}: {e}")
            return []

    def get_project_statuses(self, project_name):
        """Fetch all available statuses for a project."""
        if not self.is_connected or not project_name:
            return []
        try:
            proj = ayon_api.get_project(project_name, fields=["statuses"])
            if not proj:
                return []
            return proj.get("statuses") or []
        except Exception as e:
            self.log.error(f"Error fetching statuses for project {project_name}: {e}")
            return []

    def update_task_status(self, project_name, task_id, status):
        """Update status of a task on AYON server."""
        if not self.is_connected or not project_name or not task_id:
            return False
        try:
            ayon_api.update_task(project_name, task_id, status=status)
            return True
        except Exception as e:
            self.log.error(f"Error updating task {task_id} status to '{status}': {e}")
            return False

    def get_versions_for_product(self, project_name, product_id):
        """Fetch all version dicts for a product."""
        if not self.is_connected or not project_name or not product_id:
            return []
        try:
            return list(ayon_api.get_versions(project_name, product_ids=[product_id]))
        except Exception as e:
            self.log.error(f"Error fetching versions for product {product_id}: {e}")
            return []

    def get_representations_for_version(self, project_name, version_id):
        """Fetch all representation dicts for a version."""
        if not self.is_connected or not project_name or not version_id:
            return []
        try:
            return list(ayon_api.get_representations(project_name, version_ids=[version_id]))
        except Exception as e:
            self.log.error(f"Error fetching representations for version {version_id}: {e}")
            return []


