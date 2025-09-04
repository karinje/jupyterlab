from jupyter_server.base.handlers import APIHandler
from tornado import web
import uuid
import time


class YDocHandler(APIHandler):
    """Base handler with YDoc access"""

    @property
    def room_manager(self):
        """Access to collaborative rooms manager"""
        # Check multiple possible locations for the room manager
        app = self.application
        settings = self.settings

        # Method 1: Direct from settings
        for key in [
            "ydoc_room_manager",
            "jupyter_server_ydoc_room_manager",
            "collaborative_room_manager",
        ]:
            manager = settings.get(key)
            if manager:
                self.log.debug(f"Found room manager at settings['{key}']")
                return manager

        # Method 2: From the YDoc extension in the app
        if hasattr(app, "serverapp"):
            serverapp = app.serverapp
            for ext_name in ["jupyter_server_ydoc", "ydoc"]:
                if hasattr(serverapp, "extension_manager"):
                    ext_manager = serverapp.extension_manager
                    if hasattr(ext_manager, "extensions"):
                        ext = ext_manager.extensions.get(ext_name)
                        if ext and hasattr(ext, "room_manager"):
                            self.log.debug(
                                f"Found room manager in extension '{ext_name}'"
                            )
                            return ext.room_manager

        # Method 3: Look in the web application settings with broader search
        for key, value in settings.items():
            if "room" in key.lower() and "manager" in key.lower():
                self.log.debug(f"Found potential room manager at settings['{key}']")
                return value

        # Method 4: Try to import and get from extension directly
        try:
            from jupyter_server_ydoc import YDocExtension  # noqa: F401

            # This is a fallback - check if there's a global instance
            self.log.debug("Attempting to find YDocExtension instance")
            return None  # We'll implement this if needed
        except ImportError:
            pass

        self.log.error("Room manager not found in any expected location")
        self.log.debug(f"Available settings keys: {list(settings.keys())}")
        return None

    async def get_ydoc(self, path):
        """Get the live YDoc for a notebook using jupyter_server_ydoc API"""
        serverapp = self.settings.get("serverapp")
        from jupyter_server_ydoc import YDocExtension

        try:
            ext_app = YDocExtension.instance()
        except Exception:
            ext_app = None
        if not ext_app:
            # Try extension manager route
            ext_manager = getattr(serverapp, "extension_manager", None)
            if ext_manager and hasattr(ext_manager, "extension_apps"):
                apps = getattr(ext_manager, "extension_apps")
                if isinstance(apps, dict):
                    ext_app = apps.get("jupyter_server_ydoc")
                elif isinstance(apps, (list, set)):
                    for a in apps:
                        if a.name == "jupyter_server_ydoc":
                            ext_app = a
                            break
        if not ext_app:
            raise ValueError("Could not find active YDocExtension instance")
        # Try to get document; assume notebook json
        doc = await ext_app.get_document(
            path=path, content_type="notebook", file_format="json", copy=False
        )
        if doc is None:
            # If notebook not open yet, create room by opening
            # create a blank document room by ywebsocket_server
            encoded_path = path  # fallback
            raise ValueError("Could not get YDoc for path")
        return doc.ydoc

    def push_progress(self, event):
        """Push progress events to WebSocket"""
        progress_handler = self.settings.get("agent_progress_handler")
        if progress_handler:
            try:
                progress_handler.broadcast(event)
            except Exception as e:
                self.log.warning(f"Failed to broadcast progress event: {e}")


class InsertCellHandler(YDocHandler):
    @web.authenticated
    async def post(self):
        try:
            data = self.get_json_body()
            path = data["path"]
            index = data["index"]
            cell_type = data["cell_type"]
            source = data["source"]

            self.log.info(f"Inserting cell at index {index} in {path}")

            # Get live YDoc
            ydoc = await self.get_ydoc(path)

            # Create cell with unique ID
            cell_id = str(uuid.uuid4())

            # Create new cell dict (following nbformat structure)
            new_cell = {
                "id": cell_id,
                "cell_type": cell_type,
                "source": source if isinstance(source, list) else [source],
                "metadata": {},
            }

            # For code cells, add execution fields
            if cell_type == "code":
                new_cell["execution_count"] = None
                new_cell["outputs"] = []

            # Direct manipulation of the YDoc notebook structure
            with ydoc.begin_transaction() as txn:
                # Get cells array from YDoc
                cells = ydoc.get("cells")
                if cells is None:
                    self.log.error("No cells array found in YDoc")
                    self.set_status(500)
                    self.finish({"error": "Invalid notebook structure"})
                    return

                # Insert the new cell
                cells.insert(txn, index, new_cell)
                self.log.info(f"Cell {cell_id} inserted successfully")

            # Push progress notification
            self.push_progress(
                {
                    "type": "cell_inserted",
                    "path": path,
                    "cell_id": cell_id,
                    "index": index,
                    "timestamp": time.time(),
                }
            )

            self.finish({"cell_id": cell_id})

        except Exception as e:
            self.log.error(f"Error in InsertCellHandler: {e}")
            self.set_status(500)
            self.finish({"error": str(e)})


class UpdateCellHandler(YDocHandler):
    @web.authenticated
    async def post(self):
        try:
            data = self.get_json_body()
            path = data["path"]
            cell_id = data["cell_id"]
            source = data["source"]

            self.log.info(f"Updating cell {cell_id} in {path}")

            ydoc = await self.get_ydoc(path)

            with ydoc.begin_transaction() as txn:
                cells = ydoc.get("cells")
                if cells is None:
                    self.set_status(500)
                    self.finish({"error": "Invalid notebook structure"})
                    return

                # Find cell by ID and update source
                for i in range(len(cells)):
                    cell = cells[i]
                    if isinstance(cell, dict) and cell.get("id") == cell_id:
                        # Update source
                        source_list = source if isinstance(source, list) else [source]
                        cells[i] = {**cell, "source": source_list}
                        self.log.info(f"Cell {cell_id} updated successfully")
                        break
                else:
                    self.set_status(404)
                    self.finish({"error": "Cell not found"})
                    return

            self.push_progress(
                {
                    "type": "cell_updated",
                    "path": path,
                    "cell_id": cell_id,
                    "timestamp": time.time(),
                }
            )

            self.finish({"success": True})

        except Exception as e:
            self.log.error(f"Error in UpdateCellHandler: {e}")
            self.set_status(500)
            self.finish({"error": str(e)})


class DeleteCellHandler(YDocHandler):
    @web.authenticated
    async def post(self):
        try:
            data = self.get_json_body()
            path = data["path"]
            cell_id = data["cell_id"]

            self.log.info(f"Deleting cell {cell_id} in {path}")

            ydoc = await self.get_ydoc(path)

            with ydoc.begin_transaction() as txn:
                cells = ydoc.get("cells")
                if cells is None:
                    self.set_status(500)
                    self.finish({"error": "Invalid notebook structure"})
                    return

                # Find and delete cell
                for i in range(len(cells)):
                    cell = cells[i]
                    if isinstance(cell, dict) and cell.get("id") == cell_id:
                        cells.delete(txn, i)
                        self.log.info(f"Cell {cell_id} deleted successfully")
                        break
                else:
                    self.set_status(404)
                    self.finish({"error": "Cell not found"})
                    return

            self.push_progress(
                {
                    "type": "cell_deleted",
                    "path": path,
                    "cell_id": cell_id,
                    "timestamp": time.time(),
                }
            )

            self.finish({"success": True})

        except Exception as e:
            self.log.error(f"Error in DeleteCellHandler: {e}")
            self.set_status(500)
            self.finish({"error": str(e)})


class RunCellHandler(YDocHandler):
    @web.authenticated
    async def post(self):
        try:
            data = self.get_json_body()
            path = data["path"]
            cell_id = data["cell_id"]
            kernel_id = data.get("kernel_id")  # noqa: F841 - Will be used for kernel execution

            self.log.info(f"Running cell {cell_id} in {path}")

            # For now, just return success - we'll implement kernel execution later
            self.finish(
                {
                    "execution_count": 1,
                    "outputs": [
                        {
                            "output_type": "stream",
                            "name": "stdout",
                            "text": "Cell execution not yet implemented",
                        }
                    ],
                }
            )

        except Exception as e:
            self.log.error(f"Error in RunCellHandler: {e}")
            self.set_status(500)
            self.finish({"error": str(e)})


def setup_handlers(server_app):
    """Register handlers with the Jupyter server"""
    host_pattern = ".*$"
    base_url = server_app.web_app.settings["base_url"]

    handlers = [
        (f"{base_url}api/agent/ydoc/insert", InsertCellHandler),
        (f"{base_url}api/agent/ydoc/update", UpdateCellHandler),
        (f"{base_url}api/agent/ydoc/delete", DeleteCellHandler),
        (f"{base_url}api/agent/ydoc/run", RunCellHandler),
    ]

    server_app.web_app.add_handlers(host_pattern, handlers)
    server_app.log.info(f"Agent YDoc handlers registered: {[h[0] for h in handlers]}")

    # Log available settings for debugging
    server_app.log.debug(
        f"Available settings keys: {list(server_app.web_app.settings.keys())}"
    )
