"""Global favorites commands, independent of the gas search conversation state."""

import re


def parse_favorite_action(
    text: str | None = None,
    selection_id: str | None = None,
) -> tuple[str, int | None] | None:
    if selection_id:
        if selection_id == "fav_list":
            return ("list", None)
        match = re.fullmatch(r"fav_save_([1-5])", selection_id)
        if match:
            return ("save", int(match.group(1)))
        return None

    normalized = " ".join((text or "").casefold().split())
    if normalized in {
        "mi favorita", "mi favorito", "mis favoritas", "mis favoritos",
        "my favorite", "my favorites", "favorita", "favoritas",
        "favorito", "favoritos", "favorite", "favorites",
    }:
        return ("list", None)
    match = re.fullmatch(
        r"(?:guardar|save)(?:\s+(?:favorita|favorito|favorite))?\s+([1-5])",
        normalized,
    )
    if match:
        return ("save", int(match.group(1)))
    match = re.fullmatch(
        r"(?:eliminar|borrar)\s+(?:favorita|favorito)\s+(\d{1,2})"
        r"|remove\s+favorite\s+(\d{1,2})",
        normalized,
    )
    if match:
        return ("remove", int(match.group(1) or match.group(2)))
    return None
