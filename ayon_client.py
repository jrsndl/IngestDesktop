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

    def get_last_version(self, project_name, folder_path, product_name):
        """Get the latest version number for a product in AYON."""
        if not self.is_connected: return None
        try:
            # Get product by path
            product = ayon_api.get_product_by_path(project_name, f"{folder_path}/{product_name}")
            if not product:
                return 0
            
            # Get last version
            last_version = ayon_api.get_last_version_by_product_id(project_name, product["id"])
            if last_version:
                return last_version["version"]
            return 0
        except Exception as e:
            self.log.error(f"Error fetching last version for {folder_path}/{product_name}: {e}")
            return None
