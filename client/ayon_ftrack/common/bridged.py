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
    ft_project = find_ftrack_project(
        session, project_name, ("id", "full_name", "custom_attributes"))
    return is_project_bridged(ft_project)


_FT_ID_CHARS = set("0123456789abcdefABCDEF-")


def find_ftrack_project(session, project_name, fields=None):
    """BCN: the ftrack project of an AYON project.

    The stock lookup matches the AYON project name with the ftrack project's
    full name. That match stays first, so every project the full sync made
    behaves exactly as before. Projects created by the ftrack bridge may have
    an AYON name that differs from the ftrack full name (AYON names can't
    hold spaces); for those the ftrack project id stored on the AYON project
    ('attrib.ftrackId') is used, but only when exactly one AYON project
    carries it (presets can copy the attribute between projects).

    Args:
        session (ftrack_api.Session): ftrack session.
        project_name (str): AYON project name.
        fields (Optional[Iterable[str]]): ftrack fields to select.

    Returns:
        Union[ftrack_api.entity.base.Entity, None]: ftrack project.
    """
    if not project_name:
        return None
    select = ", ".join(fields) if fields else "id, full_name, name, custom_attributes"
    quoted = project_name.replace("\\", "\\\\").replace('"', '\\"')
    project = session.query(
        f"select {select} from Project where full_name is \"{quoted}\""
    ).first()
    if project is not None:
        return project
    try:
        import ayon_api
        ayon_project = ayon_api.get_project(
            project_name, fields={"name", "attrib.ftrackId"})
        ftrack_id = ((ayon_project or {}).get("attrib") or {}).get("ftrackId")
        if not ftrack_id or not set(ftrack_id) <= _FT_ID_CHARS:
            return None
        claimants = [
            p["name"]
            for p in ayon_api.get_projects(
                active=None, fields={"name", "attrib.ftrackId"})
            if (p.get("attrib") or {}).get("ftrackId") == ftrack_id
        ]
    except Exception:
        import logging
        logging.getLogger(__name__).warning(
            "Couldn't read the AYON project %s to find its ftrack project",
            project_name, exc_info=True)
        return None
    if claimants != [project_name]:
        return None
    return session.query(
        f"select {select} from Project where id is \"{ftrack_id}\""
    ).first()
