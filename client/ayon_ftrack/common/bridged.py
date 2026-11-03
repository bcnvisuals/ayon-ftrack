"""BCN: helpers for projects managed by the ftrack bridge.

A bridged project has the project custom attribute ``ayon_bridged`` set to
True. On such projects AYON holds only what the pipeline works on and the
link between ftrack and AYON is made by ID on the ftrack Bridge page in
AYON. Everything that mirrors the whole ftrack hierarchy, or matches
entities by name, must stay away from these projects.
"""

from .constants import CUST_ATTR_BRIDGED

BRIDGED_PROJECT_MESSAGE = (
    "This project is managed by the ftrack Bridge (ayon_bridged is on)."
    " Full syncs and name based changes are disabled for it; use the"
    " ftrack Bridge page in AYON (Studio Settings) instead."
)


def _is_true(value):
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def is_project_bridged(ft_project):
    """Is the ftrack project managed by the ftrack bridge?

    Args:
        ft_project (Union[ftrack_api.entity.base.Entity, dict, None]): ftrack
            project entity, or a dict with a "custom_attributes" mapping.
            None is treated as not bridged.

    Returns:
        bool: True when the project has 'ayon_bridged' set to True. A missing
            attribute (not created yet) means not bridged, so stock
            behaviour is unchanged until the attribute exists and is set.
    """
    if ft_project is None:
        return False
    try:
        custom_attributes = ft_project["custom_attributes"]
    except (KeyError, TypeError):
        return False
    try:
        value = custom_attributes[CUST_ATTR_BRIDGED]
    except (KeyError, TypeError):
        return False
    return _is_true(value)


def is_project_bridged_by_name(session, project_name):
    """Same as 'is_project_bridged' for a project full name.

    Args:
        session (ftrack_api.Session): ftrack session.
        project_name (str): ftrack project full name (AYON project name).

    Returns:
        bool: True when the project exists and is bridged.
    """
    if not project_name:
        return False
    quoted = project_name.replace("\\", "\\\\").replace('"', '\\"')
    ft_project = session.query(
        "select id, full_name, custom_attributes from Project"
        f" where full_name is \"{quoted}\""
    ).first()
    return is_project_bridged(ft_project)
