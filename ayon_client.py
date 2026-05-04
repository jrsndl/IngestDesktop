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
                fields=["id", "name", "path", "type", "label", "status", "parentId"]
            ))
            
            # Get all tasks
            tasks = list(ayon_api.get_tasks(
                project_name,
                fields=["id", "name", "type", "label", "status", "folderId", "assignees"]
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
            res = {}
            for prod in products:
                # Get last version
                last_v = ayon_api.get_last_version_by_product_id(project_name, prod["id"])
                v_num = last_v["version"] if last_v else 0
                f_id = str(prod["folderId"])
                res[(f_id, prod["name"], prod.get("productType"))] = v_num
            return res
        except Exception as e:
            self.log.error(f"Error fetching versions for folders {folder_ids}: {e}")
            return {}

    def get_products_for_folder(self, project_name, folder_id):
        """Get all products and their latest versions for a folder."""
        versions = self.get_last_versions(project_name, [folder_id])
        res = []
        for (f_id, name, p_type), v in versions.items():
            res.append({"name": name, "type": p_type, "version": v})
        return res
