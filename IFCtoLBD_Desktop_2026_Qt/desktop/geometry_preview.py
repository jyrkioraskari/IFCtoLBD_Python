"""Qt geometry viewport backed by the LBD OBJ Exporter renderer.

PyVista/VTK is the preferred backend and follows the implementation in
``jyrkioraskari/LBD_OBJ_Exporter``: two-sided flat-shaded surfaces, separate
opaque/translucent actors, depth peeling, silhouettes and feature outlines.
The small QPainter renderer remains as a fallback so the desktop can still be
opened before the optional 3D dependencies have been installed.
"""

from __future__ import annotations

import math
import os
from typing import Any

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QVBoxLayout, QWidget

from .geometry_data import Mesh, _rotate

os.environ.setdefault("QT_API", "pyside6")
os.environ.setdefault("MPLCONFIGDIR", "/tmp/ifctolbd_desktop_matplotlib")

try:  # Optional at import time; included by the ``desktop`` package extra.
    import numpy as np
    import pyvista as pv
    from pyvistaqt import QtInteractor
except ImportError:  # pragma: no cover - selected only in minimal installs
    np = None  # type: ignore[assignment]
    pv = None  # type: ignore[assignment]
    QtInteractor = None  # type: ignore[assignment]


PYVISTA_AVAILABLE = all(value is not None for value in (np, pv, QtInteractor))


class _SoftwareGeometryViewport(QWidget):
    """Interactive 3D viewport replicating the JavaFX geometry subscene.

    Left-drag rotates, middle/right-drag pans, and the wheel zooms. The camera
    automatically frames the model whenever geometry is loaded.
    """

    backend_name = "software"
    active_backend_name = "software"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(240)
        self.setMouseTracking(True)
        self.setStyleSheet("background-color: #f8fafc; border: 1px solid #c5d4e8; border-radius: 10px;")
        self._meshes: list[Mesh] = []
        self._message = "Select geometry and convert to preview the model."
        self._center = (0.0, 0.0, 0.0)
        self._radius = 1.0
        self._rot_x = math.radians(-20.0)
        self._rot_y = math.radians(30.0)
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._distance = 8.0
        self._dragging = False
        self._panning = False
        self._last_pos = (0.0, 0.0)

    def clear(self, message: str) -> None:
        self._meshes = []
        self._message = message
        self.update()

    def set_meshes(self, meshes: list[Mesh]) -> None:
        self._meshes = meshes
        if meshes:
            self.fit()
        else:
            self._message = ("No OBJ geometry was found in the RDF output.\n"
                             "Enable the Geometry option in Settings and run the conversion again.")
        self.update()

    def fit(self) -> None:
        if not self._meshes:
            return
        finite_vertices = [
            vertex for mesh in self._meshes for vertex in mesh.vertices
            if all(math.isfinite(component) for component in vertex)
        ]
        if not finite_vertices:
            self.clear("The OBJ geometry contains no finite vertex coordinates.")
            return
        xs = [vertex[0] for vertex in finite_vertices]
        ys = [vertex[1] for vertex in finite_vertices]
        zs = [vertex[2] for vertex in finite_vertices]
        self._center = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2)
        self._radius = max(
            math.sqrt(
                (x - self._center[0]) ** 2
                + (y - self._center[1]) ** 2
                + (z - self._center[2]) ** 2
            )
            for x, y, z in finite_vertices
        ) or 1.0
        self._rot_x = math.radians(-20.0)
        self._rot_y = math.radians(30.0)
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._dragging = event.button() == Qt.MouseButton.LeftButton
        self._panning = event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton)
        self._last_pos = (event.position().x(), event.position().y())

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if not (self._dragging or self._panning):
            return
        dx = event.position().x() - self._last_pos[0]
        dy = event.position().y() - self._last_pos[1]
        self._last_pos = (event.position().x(), event.position().y())
        if self._panning:
            self._pan_x += dx
            self._pan_y += dy
        else:
            self._rot_y += dx * 0.01
            self._rot_x = max(-math.pi / 2, min(math.pi / 2, self._rot_x - dy * 0.01))
        self.update()

    def wheelEvent(self, event) -> None:  # noqa: N802
        factor = 1.12 if event.angleDelta().y() > 0 else 0.89
        self._zoom = max(0.25, min(6.0, self._zoom * factor))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        if not self._meshes:
            painter.setPen(QColor("#667085"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._message)
            return

        width, height = self.width(), self.height()
        focal = min(width, height) * 0.9
        # Use the bounding-sphere radius so rotated corners remain inside the
        # viewport. The previous axis extent clipped tall/diagonal buildings.
        self._distance = self._radius * 2.6 / self._zoom

        light = (0.45, -0.55, -0.7)
        opaque_faces: list[tuple[float, QColor, QColor, QPolygonF]] = []
        glass_faces: list[tuple[float, QColor, QColor, QPolygonF]] = []
        for mesh in self._meshes:
            color = QColor(*mesh.color)
            edge = QColor(int(color.red() * 0.55), int(color.green() * 0.55), int(color.blue() * 0.55))
            view_points = []
            for x, y, z in mesh.vertices:
                if not all(math.isfinite(value) for value in (x, y, z)):
                    view_points.append(None)
                else:
                    view_points.append(_rotate(
                        (x - self._center[0], y - self._center[1], z - self._center[2]),
                        self._rot_x, self._rot_y,
                    ))
            translucent = mesh.opacity < 0.999
            for a, b, c in mesh.faces:
                try:
                    p1, p2, p3 = view_points[a], view_points[b], view_points[c]
                except IndexError:
                    continue
                if p1 is None or p2 is None or p3 is None:
                    continue
                u = (p2[0] - p1[0], p2[1] - p1[1], p2[2] - p1[2])
                v = (p3[0] - p1[0], p3[1] - p1[1], p3[2] - p1[2])
                normal = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
                length = math.sqrt(normal[0] ** 2 + normal[1] ** 2 + normal[2] ** 2) or 1.0
                shade = max(0.45, abs((normal[0] * light[0] + normal[1] * light[1] + normal[2] * light[2]) / length))
                polygon = QPolygonF()
                depth_sum = 0.0
                for point in (p1, p2, p3):
                    divisor = self._distance - point[2]
                    if divisor <= 0.01:
                        divisor = 0.01
                    scale = focal / divisor
                    polygon.append(QPointF(width / 2 + self._pan_x + point[0] * scale,
                                           height / 2 + self._pan_y - point[1] * scale))
                    depth_sum += divisor
                shaded = QColor(int(color.red() * shade), int(color.green() * shade), int(color.blue() * shade))
                if translucent:
                    # LBD_OBJ_Exporter glass look: alpha-blended, no fill edge.
                    alpha = max(30, int(255 * mesh.opacity))
                    shaded.setAlpha(alpha)
                    glass_faces.append((depth_sum, shaded, shaded, polygon))
                else:
                    opaque_faces.append((depth_sum, shaded, edge, polygon))

        # Opaque geometry first, translucent (windows, spaces) on top of it.
        painter.setPen(QPen(QColor(27, 38, 51, 70), 1))
        for bucket in (opaque_faces, glass_faces):
            for _, shaded, edge, polygon in sorted(bucket, key=lambda item: -item[0]):
                painter.setBrush(shaded)
                painter.setPen(QPen(edge, 1))
                painter.drawPolygon(polygon)
        painter.end()


class _PyVistaGeometryViewport(QWidget):
    """Embedded PyVista renderer ported from LBD_OBJ_Exporter's Qt viewer."""

    backend_name = "PyVista/VTK"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(240)
        self.active_backend_name = self.backend_name
        self._software_fallback: _SoftwareGeometryViewport | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.plotter = QtInteractor(self)
        layout.addWidget(self.plotter.interactor)

        self._configure_plotter()

    def _configure_plotter(self) -> None:
        self.plotter.set_background("#f2f4f5")
        self.plotter.enable_anti_aliasing()
        try:
            self.plotter.enable_depth_peeling(number_of_peels=8, occlusion_ratio=0.0)
        except Exception:
            pass
        self.plotter.show_axes()
        self.clear("Select geometry and convert to preview the model.")

    def clear(self, message: str) -> None:
        if self._software_fallback is not None:
            self._software_fallback.clear(message)
            return
        self.plotter.clear()
        self.plotter.add_text(message, position="upper_left", color="#555555", font_size=10)
        self.plotter.add_axes()
        self.plotter.render()

    def set_meshes(self, meshes: list[Mesh]) -> None:
        if not meshes:
            self.clear(
                "No OBJ geometry was found in the RDF output.\n"
                "Enable the Geometry option in Settings and run the conversion again."
            )
            return

        self.plotter.clear()
        opaque = [mesh for mesh in meshes if mesh.opacity >= 0.999]
        transparent: dict[float, list[Mesh]] = {}
        for mesh in meshes:
            if mesh.opacity < 0.999:
                transparent.setdefault(round(mesh.opacity, 3), []).append(mesh)

        if opaque:
            self._add_meshes(opaque, opacity=1.0)
        for opacity, opacity_meshes in sorted(transparent.items(), reverse=True):
            self._add_meshes(opacity_meshes, opacity=opacity)

        self.plotter.add_axes()
        self.plotter.reset_camera()
        self.plotter.render()
        if not self._render_window_is_available():
            self._activate_software_fallback(meshes)
            return

    def _render_window_is_available(self) -> bool:
        """Return false when Qt created no usable OpenGL rendering context."""
        try:
            render_window = self.plotter.render_window
            is_current = getattr(render_window, "IsCurrent", None)
            return True if not callable(is_current) else bool(is_current())
        except Exception:
            return False

    def _activate_software_fallback(self, meshes: list[Mesh]) -> None:
        """Replace an unusable OpenGL surface with the reliable Qt painter."""
        if self._software_fallback is None:
            self.plotter.interactor.hide()
            self._software_fallback = _SoftwareGeometryViewport(self)
            self.layout().addWidget(self._software_fallback)
            self.active_backend_name = "software (OpenGL unavailable)"
        self._software_fallback.set_meshes(meshes)
        self._software_fallback.show()

    def _polydata(self, meshes: list[Mesh]) -> Any:
        vertices: list[tuple[float, float, float]] = []
        faces: list[int] = []
        colors: list[tuple[int, int, int]] = []
        vertex_offset = 0
        for mesh in meshes:
            vertices.extend(mesh.vertices)
            for face in mesh.faces:
                faces.extend((3, *(index + vertex_offset for index in face)))
                colors.append(mesh.color)
            vertex_offset += len(mesh.vertices)

        points = np.asarray(vertices, dtype=float)
        face_array = np.asarray(faces, dtype=np.int64)
        polydata = pv.PolyData(points, face_array)
        polydata.cell_data["rgb"] = np.asarray(colors, dtype=np.uint8)
        return polydata

    def _add_meshes(self, meshes: list[Mesh], opacity: float) -> None:
        polydata = self._polydata(meshes)
        options = {
            "mesh": polydata,
            "scalars": "rgb",
            "rgb": True,
            "opacity": opacity,
            "show_edges": False,
            "silhouette": {"color": "#000000", "line_width": 2},
            "culling": False,
            "lighting": True,
            "smooth_shading": False,
            "preference": "cell",
            "use_transparency": opacity < 1.0,
            "force_opaque": opacity >= 1.0,
            "render": False,
        }
        try:
            actor = self.plotter.add_mesh(**options)
        except TypeError:  # Older PyVista releases lack ``silhouette``.
            options.pop("silhouette")
            actor = self.plotter.add_mesh(**options)

        material = actor.GetProperty()
        material.BackfaceCullingOff()
        material.FrontfaceCullingOff()
        material.LightingOn()
        material.SetRepresentationToSurface()
        material.SetInterpolationToFlat()
        material.SetOpacity(opacity)
        material.SetAmbient(0.35)
        material.SetDiffuse(0.75)
        material.SetSpecular(0.12)
        material.SetSpecularPower(18)
        self._add_object_outlines(polydata)

    def _add_object_outlines(self, polydata: Any) -> None:
        try:
            outlines = polydata.extract_feature_edges(
                boundary_edges=True,
                feature_edges=True,
                manifold_edges=False,
                non_manifold_edges=True,
                feature_angle=25,
            )
        except Exception:
            return
        if getattr(outlines, "n_cells", 0):
            self.plotter.add_mesh(
                outlines, color="#000000", line_width=4, render=False
            )

    def fit(self) -> None:
        if self._software_fallback is not None:
            self._software_fallback.fit()
            return
        self.plotter.reset_camera()
        self.plotter.render()

    def close(self) -> None:
        self.plotter.close()
        super().close()


GeometryViewport = (
    _PyVistaGeometryViewport if PYVISTA_AVAILABLE else _SoftwareGeometryViewport
)
