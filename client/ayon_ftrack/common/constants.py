# Name of attribute on server where ftrack related info is stored
FTRACK_ID_ATTRIB = "ftrackId"
FTRACK_PATH_ATTRIB = "ftrackPath"
REMOVED_ID_VALUE = "removed"

# Custom attribute where server id is stored
CUST_ATTR_KEY_SERVER_ID = "ayon_id"
CUST_ATTR_KEY_SERVER_PATH = "ayon_path"
CUST_ATTR_KEY_LIST_TYPE = "ayon_list_type"
CUST_ATTR_KEY_SYNC_FAIL = "ayon_sync_failed"

# Group which marks custom attribute to synchronize
CUST_ATTR_GROUP = "ayon"

# Project custom attribute which define if project should be auto-synced
CUST_ATTR_AUTO_SYNC = "auto_sync_enabled"

# BCN: project custom attribute which marks a project as managed by the
#   ftrack bridge (selective links instead of a full mirror). Full syncs,
#   'Prepare project', event sync and name based lookups are disabled on
#   bridged projects, because they would rename or deactivate AYON data.
CUST_ATTR_BRIDGED = "ayon_bridged"

FPS_KEYS = {
    "fps",
    "fps_string"
}

# Intent custom attribute name
CUST_ATTR_INTENT = "intent"
