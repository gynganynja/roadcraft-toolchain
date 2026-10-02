"""Blender-side lamp geometry for ``roadcraft.lamps``. Run inside Blender (``bpy`` is imported on use).

* ``lit_copy``   coincident lit copy of an unlit lens: the Lada's ``<name>_on`` objects for lens states.
* ``lit_shell``  lit copy pushed out along its normals (1 mm): the overlay a strobe or beacon flashes over a lens
                 that stays (L275 v8/v9 beacon). Never flash the unlit lens itself.
* ``join_lens``  join an extra lens (an accessory light bar's stop/tail or reverse lens) into an existing lamp
                 object as another material slot, so the existing show/hide nodes switch it (L275 v6).
* ``material_conflicts``  the exporter keeps one material per texture in an object: check before export.

Lit objects stay default-visible in the model markup (the graph's init hides them). ``hide_render`` only keeps
them out of Blender previews; it does not reach the export.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping

from . import lamps


def _duplicate(obj: Any, material: Any, name: str) -> Any:
    import bpy
    copy = obj.copy()
    copy.data = obj.data.copy()
    copy.name = copy.data.name = name
    copy.data.materials.clear()
    copy.data.materials.append(material)
    copy.data.polygons.foreach_set("material_index", [0] * len(copy.data.polygons))
    for collection in obj.users_collection or [bpy.context.collection]:
        collection.objects.link(copy)
    copy.hide_render = True
    return copy


def lit_copy(obj: Any, material: Any, name: str) -> Any:
    """Coincident copy of ``obj`` on the lit ``vehicle_lights`` material. Name it ``<lens>_on_LODn``."""
    return _duplicate(obj, material, name)


def lit_shell(obj: Any, material: Any, name: str, offset: float = .001) -> Any:
    """Copy of ``obj`` pushed ``offset`` metres out along its vertex normals, on the lit material: shown over the
    lens without depth fighting, and the lens stays visible when it is hidden. Normals must face outward."""
    import bmesh
    shell = _duplicate(obj, material, name)
    bm = bmesh.new()
    bm.from_mesh(shell.data)
    bm.normal_update()
    for vertex in bm.verts:
        vertex.co += vertex.normal * offset
    bm.to_mesh(shell.data)
    bm.free()
    shell.data.update()
    return shell


def join_lens(target: Any, piece: Any) -> Any:
    """Join ``piece`` into ``target`` (same LOD). The piece's UV channel takes the target's name first: a join with
    differently named channels adds a second channel and the game reads the empty first one (L275 v6)."""
    import bpy
    piece.data.uv_layers[0].name = target.data.uv_layers[0].name
    bpy.ops.object.select_all(action="DESELECT")
    target.select_set(True)
    piece.select_set(True)
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.join()
    return target


def base_texture(material: Any) -> str | None:
    """Name of the image feeding the material's base colour (the exporter's split key), or the first image."""
    if material is None or not material.use_nodes:
        return None
    images = [n for n in material.node_tree.nodes if n.type == "TEX_IMAGE" and n.image]
    for node in images:
        if any(link.to_socket.name == "Base Color" for out in node.outputs for link in out.links):
            return node.image.name
    return images[0].image.name if images else None


def material_conflicts(preset_of: Mapping[str, str] | Callable[[str], str | None],
                       texture_of: Callable[[Any], str | None] = base_texture, *, suffix: str = "_LOD") -> list[dict]:
    """``lamps.material_conflicts`` over the scene's export meshes (names containing ``suffix``). ``preset_of``
    maps a material name to its preset (``vehicle_body``, ``vehicle_glass_outer``, ``vehicle_lights``, ...)."""
    import bpy
    lookup = preset_of.get if isinstance(preset_of, Mapping) else preset_of
    objects = {}
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or suffix not in obj.name:
            continue
        rows = []
        for material in obj.data.materials:
            preset = lookup(material.name) if material else None
            texture = texture_of(material) if material else None
            if preset and texture:
                rows.append((material.name, texture, preset))
        objects[obj.name] = rows
    return lamps.material_conflicts(objects)
