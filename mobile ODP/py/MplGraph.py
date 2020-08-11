import os
import logging
import unittest
import re

import pandas as pd
import arrow
import numpy as np
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from matplotlib import gridspec
from matplotlib import ticker
from matplotlib.ticker import ScalarFormatter, FormatStrFormatter
import matplotlib.ticker as ticker
from matplotlib.widgets import RectangleSelector
from matplotlib.patches import Rectangle

from PyQt5.QtCore import pyqtProperty, pyqtSignal, pyqtSlot, QObject, QVariant, QThread
from PyQt5.QtQml import QJSValue
from PyQt5.QtGui import QPolygonF, QPainter, QCursor
from PyQt5.QtWidgets import QApplication, QWidget, QGridLayout, QMainWindow, QSizePolicy
from PyQt5.QtCore import Qt


DOWNCAST_COLOR = 'b'
UPCAST_COLOR = 'g'
INVALID_COLOR = 'r'

DOWNCAST_SECOND_COLOR = 'xkcd:light blue'
UPCAST_SECOND_COLOR = 'xkcd:light green'


class MplGraph(QObject):

    valids_invalids_changed = pyqtSignal(str, str, QVariant, QVariant,
                                        arguments=["x", "y",
                                                   "new_valid_xy_values", "new_invalid_xy_values"])
    cursor_moved = pyqtSignal(float, float, arguments=["x", "y"])

    def __init__(self, qml_item=None, graph_name=None, df=None,
                 tool_mode="pan", show_invalids=False, show_tooltips=False):
        super().__init__()

        self.qml_item = qml_item        # QML Item
        self.graph_name = graph_name
        self.df = df                  # Dataframe containing the data to plot
        self._tool_mode = tool_mode
        self._show_invalids = show_invalids
        self._show_tooltips = show_tooltips
        self._downcast_visibility = True
        self._upcast_visibility = False

        # Matplotlib Figure
        self.figure = self.qml_item.getFigure()
        self.figure.tight_layout()
        self.figure.subplots_adjust(left=0.15,right=0.95,bottom=0.1,top=0.95)

        # Matplotlib Canvas
        self.canvas = None
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.canvas.updateGeometry()
        # self.canvas.setFocusPolicy(Qt.ClickFocus)
        # self.canvas.setFocus()

        # Setup the matplotlib axis
        self.axis = self.figure.add_subplot(111) #, facecolor='lightblue')
        self.axis.xaxis.set_major_formatter(FormatStrFormatter('%.3f'))
        self.axis.yaxis.set_major_formatter(FormatStrFormatter('%.3f'))

        # Set up an annotation for show onHover tooltips
        self.annotation = self.axis.annotate("", xy=(0, 0), xytext=(20, 20),
                                             textcoords="offset points",
                                             bbox=dict(boxstyle="round", fc="w",
                                                       facecolor="white", alpha=0.4),
                                             arrowprops=dict(arrowstyle="->"))
        self.annotation.set_visible(show_tooltips)

        # Set variables for use during different mouse events
        self._zoom_scale = 1.4                  # Controls the rate for zooming in on_scroll event
        self._is_pressed = False                # Used for panning in the map
        self.cur_xlim = None
        self.cur_ylim = None
        self.xpress = None
        self.ypress = None
        self._pick_event = False                # Used for on_pick MPL event
        self._is_drawing = False
        self.cur_rect = None

        self.cur_x = None
        self.cur_y = None

        # Connect mouse events to methods
        self.qml_item.mpl_connect('button_press_event', self.on_press)
        self.qml_item.mpl_connect('button_release_event', self.on_release)
        self.qml_item.mpl_connect("motion_notify_event", self.on_motion)
        self.qml_item.mpl_connect('scroll_event', self.on_scroll)
        self.qml_item.mpl_connect('figure_leave_event', self.on_figure_leave)
        # self.qml_item.mpl_connect('key_release_event', self.on_key_release)
        # self.canvas.mpl_connect('key_release_event', self.on_key_release)

    # Plotting the graph
    def plot_graph(self, x=None, y=None, title=None):
        """
        Method to load a new graph to the figure
        :param x:
        :param y:
        :return:
        """

        """
        Need to check on the following:
        - Labels / Title - don't override with a (Secondary) label, use only the primary ones
        - Different x / y - if the graph already has x/y labels, and those provided are different, 
                            don't plot (that'd be like plotting Temperature + Conductivity on the same graph
        - x/y is missing in the data frame - don't plot

        """
        # logging.info(f"Plotting {self.graph_name}, {self.qml_item}, {x}, {y}")

        # Set chart / axes labels and axes formatting
        x_label = x.replace("(Secondary)", "").strip()
        y_label = y.replace("(Secondary)", "").strip()
        label = f"{x_label} v. {y_label}"

        # logging.info(f"label={label}")
        # logging.info(f"get_xlabel={self.axis.get_xlabel()}, get_label={self.axis.get_ylabel()}")

        # logging.info(f"\tPlotting variables in {self.graph_name} > {x} v. {y}")

        # Check the x / y labels have been set or not
        if self.axis.get_xlabel() == "" or self.axis.get_ylabel() == "":

            self.axis.set_xlabel(x_label)
            self.axis.set_ylabel(y_label)
            if title is None:
                title = label
            self.axis.set_title(title)
            if "depth" in y.lower() or "descent rate" in y.lower():
                self.axis.yaxis.set_major_formatter(FormatStrFormatter('%.2f'))

        if x not in self.df or y not in self.df:
            logging.error(
                f"Skipping plotting, variables not found in the dataframe for {self.graph_name}: {x}, {y}")
            return

        # TODO Todd Hay - ODP-32
        # if (self.axis.get_xlabel() != "" and x_label != self.axis.get_xlabel()) or \
        #         (self.axis.get_ylabel() != "" and y_label != self.axis.get_ylabel()):
        #     logging.error(
        #         f"Skipping plotting, trying to plot different variables for {self.graph_name} > {x_label} x {y_label}")
        #     return

        # Color
        # self.df.loc[:, "color"] = self.df.loc[:, "color"].assign()

        # Valid & Invalid data mask
        # mask = (~self.df[f"{x} invalid"]) & (~self.df[f"{y} invalid"])
        mask = (~self.df[f"{x} invalid"])
        df_valids = self.df.loc[mask]
        df_invalids = self.df.loc[~mask]

        # Set the X / Y axes extents to the limit of the valid data points
        min_y = df_valids.loc[:, [y, y_label]].min(axis=1).min()
        max_y = df_valids.loc[:, [y, y_label]].max(axis=1).max()
        min_x = df_valids.loc[:, [x, x_label]].min(axis=1).min()
        max_x = df_valids.loc[:, [x, x_label]].max(axis=1).max()

        buffer = 0.1
        self.axis.set_xlim((1-buffer) * min_x, (1+buffer) * max_x)
        if "depth" in y.lower():
            self.axis.set_ylim((1+buffer) * max_y, (1-buffer) * min_y)
        else:
            self.axis.set_ylim((1-buffer) * min_y, (1+buffer) * max_y)

        self.axis.tick_params(direction='out', length=6, width=1, grid_alpha=0.5)
        self.axis.minorticks_on()
        self.axis.grid(which='major', linestyle='-', linewidth=0.5, color='black')
        self.axis.grid(which='minor', linestyle='dashed', linewidth=0.25, color='gray')

        # Plot the valid line
        try:
            mask = (df_valids["is_downcast"] == 1)
            df_valids_downcast = df_valids.loc[mask]
            df_valids_upcast = df_valids.loc[~mask]

            if "Secondary" in x:
                down_color = DOWNCAST_SECOND_COLOR
                up_color = UPCAST_SECOND_COLOR
            else:
                down_color = DOWNCAST_COLOR
                up_color = UPCAST_COLOR

            valids_downcast_line = self.axis.plot(df_valids_downcast[x], df_valids_downcast[y],
                                                  visible=self._downcast_visibility, label=f"{x} downcast",
                                                  marker='o', markersize=3, color=down_color)
            valids_upcast_line = self.axis.plot(df_valids_upcast[x], df_valids_upcast[y],
                                                visible=self._upcast_visibility, label=f"{x} upcast",
                                                marker='o', markersize=3, color=up_color)

        except Exception as ex:
            logging.error(f"error plotting valid line: {ex}")

        # Plot the invalid line
        try:
            mask = (df_invalids["is_downcast"] == 1)
            df_invalids_downcast = df_invalids.loc[mask]
            df_invalids_upcast = df_invalids.loc[~mask]
            visibility = self._show_invalids and self._downcast_visibility
            invalid_downcast_line = self.axis.plot(df_invalids_downcast[x], df_invalids_downcast[y],
                                                   visible=visibility, label=f"{x} downcast invalid",
                                                   marker='x', markersize=3, linestyle='None', color=INVALID_COLOR)
            visibility = self._show_invalids and self._upcast_visibility
            invalid_upcast_line = self.axis.plot(df_invalids_upcast[x], df_invalids_upcast[y],
                                                 visible=visibility, label=f"{x} upcast invalid",
                                                 marker='x', markersize=3, linestyle='None', color=INVALID_COLOR)

        except Exception as ex:
            logging.error(f"error plotting invalid line: {ex}")

        self.qml_item.draw_idle()

    # Toggling Legend and Invalid Data Points
    def toggle_legend(self, status):
        """
        Method to turn the legend on and off.  On the first call, this will create the legend for the graph axis
        :param status:
        :return:
        """
        if not isinstance(status, bool):
            return

        leg = self.axis.get_legend()
        if leg:
            leg.set_visible(status)
        else:
            self.axis.legend(loc='lower right')

        self.qml_item.draw_idle()

    def toggle_invalids(self, visibility):
        """
        Method to toggle the invalids on/off
        :param visibility: bool - True - show them / False - hide them
        :return:
        """
        if not isinstance(visibility, bool):
            return

        self._show_invalids = visibility

        invalid_lines = [x for x in self.axis.lines if "invalid" in x.get_label()]
        for line in invalid_lines:
            if "downcast invalid" in line.get_label():
                new_status = self._downcast_visibility and self._show_invalids
            elif "upcast invalid" in line.get_label():
                new_status = self._upcast_visibility and self._show_invalids
            line.set_visible(new_status)

        # Refresh the graphs
        self.qml_item.draw_idle()

    def toggle_upcast_downcast(self, value):
        """
        Method to toggle between upcast, downcast, and both
        :param status: enumerated value - up, down, updown
        :return:
        """
        if value not in ["up", "down", "updown"]:
            logging.error(f"Incorrect value provide for toggling upcast/downcast: {ex}")
            return

        self._downcast_visibility = False
        self._upcast_visibility = False

        if value in ["down", "updown"]:
            self._downcast_visibility = True
        if value in ["up", "updown"]:
            self._upcast_visibility = True

        for l in self.axis.lines:
            if "downcast invalid" in l.get_label():
                new_status = self._downcast_visibility and self._show_invalids
            elif "upcast invalid" in l.get_label():
                new_status = self._upcast_visibility and self._show_invalids
            elif "downcast" in l.get_label():
                new_status = self._downcast_visibility
            elif "upcast" in l.get_label():
                new_status = self._upcast_visibility

            # logging.info(f"{l.get_label()} > {new_status}")
            l.set_visible(new_status)

        self.qml_item.draw_idle()

    # Mouse Events
    def on_press(self, event):
        """
        Matplotlib button_press_event
        :param event:
        :return:
        """
        # if self._pick_event:
        #     self._pick_event = False
        #     logging.info(f"pick event is false")
        #     return
        # if self.canvas.widgetlock.locked(): return

        if event.inaxes is None: return

        gca = event.inaxes
        self.xpress = event.xdata
        self.ypress = event.ydata

        if self._tool_mode in ["pan", "zoomVertical", "zoomHorizontal"]:
            QApplication.setOverrideCursor(QCursor(Qt.OpenHandCursor))
            self._is_pressed = True
            self.cur_xlim = gca.get_xlim()
            self.cur_ylim = gca.get_ylim()

        elif self._tool_mode == "invalidData":
            QApplication.setOverrideCursor(QCursor(Qt.CrossCursor))
            self._is_drawing = True
            self.cur_rect = Rectangle((0, 0), 1, 1, color='lightblue', zorder=100, visible=True, alpha=0.7)
            gca.add_patch(self.cur_rect)

    def on_release(self, event):
        """
        Matplotlib button_release_event
        :param event:
        :return:
        """
        QApplication.setOverrideCursor(QCursor(Qt.ArrowCursor))

        if self._tool_mode in ["pan", "zoomVertical", "zoomHorizontal"]:

            self._is_pressed = False

        elif self._tool_mode == "invalidData":

            if event.inaxes is None: return

            gca = event.inaxes

            self._is_drawing = False
            if self.cur_rect.get_x() != 0 and self.cur_rect.get_width() != 1:

                # Delete the selection rectangle and refresh the map display
                del gca.patches[:]
                self.qml_item.draw_idle()

                # Get the x/y min/max of the currently drawn selection rectangle
                x_min, x_max = sorted([self.cur_rect.get_x(), self.cur_rect.get_x() + self.cur_rect.get_width()])
                y_min, y_max = sorted([self.cur_rect.get_y(), self.cur_rect.get_y() + self.cur_rect.get_height()])

                valid_lines = [x for x in gca.lines if "invalid" not in x.get_label()]
                for valid_line in valid_lines:

                    # Get the label for the valid line
                    label = valid_line.get_label()

                    if "downcast" in label and not self._downcast_visibility:
                        continue
                    elif "upcast" in label and not self._upcast_visibility:
                        continue

                    logging.info(f"label = {label},  upcast = {self._upcast_visibility}, "
                                 f"downcast = {self._downcast_visibility}")

                    # Find the selected valid points that need to be converted to invalid points
                    valid_xy_data = valid_line.get_xydata()
                    new_invalid_xy_values = [[pt[0], pt[1]] for pt in valid_xy_data
                                              if (x_min <= pt[0] <= x_max) and (y_min <= pt[1] <= y_max)]

                    # Find the selected invalid points that need to be converted to valid points
                    new_valid_xy_values = []
                    invalid_lines = [x for x in gca.lines if x.get_label() == f"{label} invalid"]
                    if len(invalid_lines) == 1:
                        invalid_line = invalid_lines[0]
                        invalid_xy_data = invalid_line.get_xydata()
                        new_valid_xy_values = [[pt[0], pt[1]] for pt in invalid_xy_data
                                                if (x_min <= pt[0] <= x_max) and (y_min <= pt[1] <= y_max)]

                    # With the new xy values, update the dataframe and then redraw the two graphs based on the dataframe
                    # Update the dataframe with the new valid and invalid values

                    # Continue processing this data series only if new invalid or valid points exist
                    if len(new_invalid_xy_values) > 0 or len(new_valid_xy_values) > 0:

                        # Get the column names for the X / Y axes and their associated invalid columns
                        # x, y = [f"{x.strip()}" for x in self.axis.get_label().split("v.")]
                        x = valid_line.get_label()
                        y = self.axis.get_ylabel()

                        self.valids_invalids_changed.emit(x, y, new_valid_xy_values, new_invalid_xy_values)

    def on_motion(self, event):
        """
        Matplotlib motion_notify_event
        :param event:
        :return:
        """
        gca = event.inaxes

        self.cur_x = event.xdata
        self.cur_y = event.ydata

        if self._tool_mode in ["pan", "zoomVertical", "zoomHorizontal"]:

            if self._is_pressed:
                # Pan the Map

                if event.inaxes is None or self.xpress is None or self.ypress is None: return
                dx = event.xdata - self.xpress
                dy = event.ydata - self.ypress
                self.cur_xlim -= dx
                self.cur_ylim -= dy
                gca.set_xlim(self.cur_xlim)
                gca.set_ylim(self.cur_ylim)
                self.qml_item.draw_idle()

            else:
                # OnHover, read out value of data to statusbar

                if not gca: return

                for line in self.axis.get_lines():
                    if line.contains(event)[0]:
                        self.cursor_moved.emit(round(event.xdata, 4),
                                               round(event.ydata, 4))
                        if self._show_tooltips:
                            self.update_annotation(round(event.xdata, 4),
                                               round(event.ydata, 4))
                    else:
                        self.annotation.set_visible(False)
                        self.qml_item.draw_idle()

        elif self._tool_mode == "invalidData":

            if self._is_drawing and event.xdata and event.ydata:

                self.cur_rect.set_width(event.xdata- self.xpress)
                self.cur_rect.set_height(event.ydata - self.ypress)
                self.cur_rect.set_xy((self.xpress, self.ypress))
                self.qml_item.draw_idle()

    def on_scroll(self, event):
        """
        Matplotlib scroll_event
        :param event:
        :return:
        """
        gca = event.inaxes
        if not gca: return

        cur_xlim = gca.get_xlim()
        cur_ylim = gca.get_ylim()

        xdata = event.xdata  # get event x location
        ydata = event.ydata  # get event y location

        if event.button == 'down':
            # deal with zoom out
            scale_factor = self._zoom_scale
        elif event.button == 'up':
            # deal with zoom in
            scale_factor = 1 / self._zoom_scale
        else:
            # deal with something that should never happen
            scale_factor = 1
            # print (event.button)

        new_width = (cur_xlim[1] - cur_xlim[0]) * scale_factor
        new_height = (cur_ylim[1] - cur_ylim[0]) * scale_factor

        relx = (cur_xlim[1] - xdata) / (cur_xlim[1] - cur_xlim[0])
        rely = (cur_ylim[1] - ydata) / (cur_ylim[1] - cur_ylim[0])

        if self._tool_mode in ["pan", "zoomHorizontal", "invalidData"]:
            gca.set_xlim([xdata - new_width * (1 - relx), xdata + new_width * (relx)])
        if self._tool_mode in ["pan", "zoomVertical", "invalidData"]:
            gca.set_ylim([ydata - new_height * (1-rely), ydata + new_height * (rely)])

        # gca.set_xlim([xdata - new_width * (1 - relx), xdata + new_width * (relx)])
        # gca.set_ylim([ydata - new_height * (1 - rely), ydata + new_height * (rely)])

        self.qml_item.draw()

    def on_figure_leave(self, event):
        """
        Method called when the cursor leaves the figure
        :param event:
        :return:
        """
        QApplication.setOverrideCursor(QCursor(Qt.ArrowCursor))

    # Key Events
    def key_zoom(self, action):
        """
        Method called when a key is released on the graph
        :param action:
        :return:
        """
        if self.cur_x is None or self.cur_y is None:
            return

        if action not in ["zoom in", "zoom out"]:
            return

        cur_xlim = self.axis.get_xlim()
        cur_ylim = self.axis.get_ylim()

        if action == "zoom out":
            scale_factor = self._zoom_scale
        elif action == "zoom in":
            scale_factor = 1 / self._zoom_scale
        else:
            scale_factor = 1

        new_width = (cur_xlim[1] - cur_xlim[0]) * scale_factor
        new_height = (cur_ylim[1] - cur_ylim[0]) * scale_factor

        relx = (cur_xlim[1] - self.cur_x) / (cur_xlim[1] - cur_xlim[0])
        rely = (cur_ylim[1] - self.cur_y) / (cur_ylim[1] - cur_ylim[0])

        if self._tool_mode in ["pan", "zoomHorizontal", "invalidData"]:
            self.axis.set_xlim([self.cur_x - new_width * (1 - relx), self.cur_x + new_width * (relx)])
        if self._tool_mode in ["pan", "zoomVertical", "invalidData"]:
            self.axis.set_ylim([self.cur_y - new_height * (1 - rely), self.cur_y + new_height * (rely)])

        self.qml_item.draw()

    def update_annotation(self, x, y):
        """
        Method to update the annotation for the tooltip
        :param x: x value, as a float
        :param y: y value, as a float
        :return:
        """
        self.annotation.xy = [x, y]
        self.annotation.set_text(f"{self.axis.get_xlabel()}: {x}\n"
                                 f"{self.axis.get_ylabel()}: {y}")
        self.annotation.set_visible(True)
        self.qml_item.draw()

    def toggle_tooltips(self, visibility=False):
        """
        Method to toggle the self.annotation which is the tooltip for displaying
        the dynamic x/y values of the graph when the cursor moves
        :param visibility:
        :return:
        """
        if not isinstance(visibility, bool):
            logging.error(f"Error updating the graph tooltip visibility, not a boolean value")
            return

        self._show_tooltips = visibility
        self.annotation.set_visible(visibility)
