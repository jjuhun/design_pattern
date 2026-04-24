from PySide6.QtGui import QColor
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem, QListWidgetItem

from dialogs.class_dialog import ClassDialog


class ClassController:
    def __init__(self, window):
        self.window = window

    def connect_signals(self):
        panel = self.window.class_panel
        panel.add_class_btn.clicked.connect(self.add_class)
        panel.edit_class_btn.clicked.connect(self.edit_selected_class)
        panel.remove_class_btn.clicked.connect(self.remove_selected_class)
        panel.class_table.cellClicked.connect(self.on_class_selected)
        panel.class_table.cellDoubleClicked.connect(self.on_class_double_clicked)

    def refresh_class_table(self):
        panel = self.window.class_panel
        panel.class_table.setRowCount(0)

        for item in self.window.class_manager.get_classes():
            row = panel.class_table.rowCount()
            panel.class_table.insertRow(row)

            class_id = item["class_id"]
            class_name = item["name"]
            class_count = (
                self.window.annotation_manager.count_boxes_by_class_id(class_id)
                + self.window.annotation_manager.count_polygons_by_class_id(class_id)
            )

            color_item = QTableWidgetItem()
            color_item.setBackground(QColor(item["color"]))
            color_item.setText("   ")
            color_item.setData(Qt.UserRole, class_id)

            id_item = QTableWidgetItem(str(class_id))
            id_item.setData(Qt.UserRole, class_id)

            name_item = QTableWidgetItem(class_name)
            name_item.setData(Qt.UserRole, class_id)

            count_item = QTableWidgetItem(str(class_count))
            count_item.setData(Qt.UserRole, class_id)

            panel.class_table.setItem(row, 0, color_item)
            panel.class_table.setItem(row, 1, id_item)
            panel.class_table.setItem(row, 2, name_item)
            panel.class_table.setItem(row, 3, count_item)

    def get_selected_class_row(self):
        items = self.window.class_panel.class_table.selectionModel().selectedRows()
        if not items:
            return None
        return items[0].row()

    def get_selected_class_id_from_row(self, row):
        item = self.window.class_panel.class_table.item(row, 1)
        if item is None:
            return None
        return item.data(Qt.UserRole)

    def add_class(self):
        name = self.window.class_panel.class_name_edit.text().strip()
        ok, _, err = self.window.class_manager.add_class(name)
        if not ok:
            self.window.simple_info(err)
            return
        self.window.class_panel.class_name_edit.clear()
        self.refresh_class_table()
        self.window.update_status_only()

    def edit_selected_class(self):
        row = self.get_selected_class_row()
        if row is None:
            self.window.simple_info("Please select a class to edit.")
            return

        old_class_id = self.get_selected_class_id_from_row(row)
        old_name = self.window.class_manager.get_class_name(old_class_id)

        dialog = ClassDialog(
            title="Edit Class",
            class_id=old_class_id,
            name=old_name,
            parent=self.window,
        )

        if dialog.exec():
            new_class_id = dialog.get_class_id()
            new_name = dialog.get_name()
            ok, err = self.window.class_manager.edit_class(old_class_id, new_class_id, new_name)
            if not ok:
                self.window.simple_info(err)
                return

            if new_class_id != old_class_id:
                self.window.annotation_manager.replace_class_id_in_boxes(old_class_id, new_class_id)
                self.window.annotation_manager.replace_class_id_in_polygons(old_class_id, new_class_id)

            self.refresh_class_table()
            self.refresh_object_list()
            self.window.refresh_all_views()
            self.window.add_log(f"Edited class [{old_class_id}] -> [{new_class_id}] {new_name}")

    def remove_selected_class(self):
        row = self.get_selected_class_row()
        if row is None:
            self.window.simple_info("Please select a class to remove.")
            return

        class_id = self.get_selected_class_id_from_row(row)
        self.window.annotation_manager.remove_boxes_by_class_id(class_id)
        self.window.annotation_manager.remove_polygons_by_class_id(class_id)

        ok, err = self.window.class_manager.remove_class(class_id)
        if not ok:
            self.window.simple_info(err)
            return

        self.refresh_class_table()
        self.refresh_object_list()
        self.window.refresh_all_views()
        self.window.add_log(f"Removed class [{class_id}]")

    def on_class_selected(self, row, _column):
        class_id = self.get_selected_class_id_from_row(row)
        if class_id is not None:
            self.window.class_manager.select_class(class_id)
            self.window.update_status_only()
            self.refresh_object_list()
            self.window.add_log(
                f'Selected class: [{class_id}] {self.window.class_manager.get_class_name(class_id)}'
            )

    def on_class_double_clicked(self, row, _column):
        class_id = self.get_selected_class_id_from_row(row)
        if class_id is None:
            return
        self.window.class_manager.select_class(class_id)
        self.edit_selected_class()

    def refresh_object_list(self):
        panel = self.window.class_panel
        panel.object_list.clear()

        class_id = self.window.class_manager.get_selected_class_id()
        if class_id is None:
            return

        objects = self.window.annotation_manager.get_items_by_class_id(class_id)
        for obj in objects:
            item_type = obj["item_type"]
            item_id = obj["item_id"]
            label = "Box" if item_type == "box" else "Polygon"
            text = f'Frame {obj["frame_idx"]} | {label} {item_id}'
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, {"item_type": item_type, "item_id": item_id})
            panel.object_list.addItem(item)
