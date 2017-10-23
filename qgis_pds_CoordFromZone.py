# -*- coding: utf-8 -*-

import os
import numpy
from qgis.core import *
from qgis.gui import QgsMessageBar
from PyQt4 import QtGui, uic
from PyQt4.QtGui import *
from PyQt4.QtCore import *

from QgisPDS.db import Oracle
from QgisPDS.connections import create_connection
from QgisPDS.utils import to_unicode
from QgisPDS.tig_projection import *

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'qgis_pds_zonations_base.ui'))

class QgisPDSCoordFromZoneDialog(QtGui.QDialog, FORM_CLASS):
    def __init__(self, _project, _iface, _editLayer, parent=None):
        """Constructor."""
        super(QgisPDSCoordFromZoneDialog, self).__init__(parent)

        self.setupUi(self)

        self.mParameterFrame.setVisible(False)
        self.mWellsListWidget.setVisible(False)
        self.mWellLabel.setVisible(False)

        self.plugin_dir = os.path.dirname(__file__)
        self.iface = _iface
        self.project = _project
        self.editLayer = _editLayer

        try:
            connection = create_connection(self.project)
            scheme = self.project['project']

            self.db = connection.get_db(scheme)
        except Exception as e:
            self.errorMessage(self.tr(u'Project {0}: {1}').format(scheme, str(e)))
            return

        self.proj4String = 'epsg:4326'
        try:
            self.tig_projections = TigProjections(db=self.db)
            proj = self.tig_projections.get_projection(self.tig_projections.default_projection_id)
            if proj is not None:
                self.proj4String = 'PROJ4:'+proj.qgis_string
                destSrc = QgsCoordinateReferenceSystem()
                destSrc.createFromProj4(proj.qgis_string)
                sourceCrs = QgsCoordinateReferenceSystem('epsg:4326')
                self.xform = QgsCoordinateTransform(sourceCrs, destSrc)
        except Exception as e:
            self.iface.messageBar().pushMessage(self.tr("Error"),
                                                self.tr(u'Project projection read error {0}: {1}').format(
                                                scheme, str(e)),
                                                level=QgsMessageBar.CRITICAL)

        settings = QSettings()
        selectedZonations = settings.value("/PDS/Zonations/SelectedZonations", [])
        selectedZones = settings.value("/PDS/Zonations/selectedZones", [])

        self.selectedZonations = [int(z) for z in selectedZonations]
        self.selectedZones = [int(z) for z in selectedZones]


        self.fillZonations()

    def errorMessage(self, msg):
        self.iface.messageBar().pushMessage(self.tr("Error"), msg, level=QgsMessageBar.CRITICAL)

    def get_sql(self, value):
        sql_file_path = os.path.join(self.plugin_dir, 'db', value)
        with open(sql_file_path, 'rb') as f:
            return f.read().decode('utf-8')

    def on_buttonBox_accepted(self):
        self.process()


    def process(self):
        selectedZonations = []
        selectedZones = []
        for si in self.zonationListWidget.selectedItems():
            selectedZonations.append(int(si.data(Qt.UserRole)))

        self.editLayer.startEditing()
        iter = self.editLayer.dataProvider().getFeatures()

        sel = None
        for zones in self.zoneListWidget.selectedItems():
            sel = zones.data(Qt.UserRole)
            selectedZones.append(sel[0])

        if sel is None:
            return

        idxMd = self.editLayer.dataProvider().fieldNameIndex('MD')
        idxTvd = self.editLayer.dataProvider().fieldNameIndex('TVD')
        if idxMd < 0:
            self.editLayer.dataProvider().addAttributes([QgsField("MD", QVariant.Double)])
        if idxTvd < 0:
            self.editLayer.dataProvider().addAttributes([QgsField("TVD", QVariant.Double)])

        idx1 = self.editLayer.dataProvider().fieldNameIndex('Well identifier')
        for feature in iter:
            if idx1 >= 0:
                wellId = feature[u'Well identifier']
            else:
                wellId = feature['well_id']

            coords = self._getCoords(sel, wellId)
            if coords is not None:
                geom = QgsGeometry.fromPoint(coords)
                self.editLayer.changeGeometry(feature.id(), geom)

        self.editLayer.commitChanges()

        settings = QSettings()
        settings.setValue("/PDS/Zonations/SelectedZonations", selectedZonations)
        settings.setValue("/PDS/Zonations/selectedZones", selectedZones)


    def on_zonationListWidget_itemSelectionChanged(self):
        self.zoneListWidget.clear()
        for si in self.zonationListWidget.selectedItems():
            self._fillZones(int(si.data(Qt.UserRole)))


    def _getCoords(self, zoneDef, wellId):
        sqlFile = os.path.join(self.plugin_dir, 'db', 'ZonationCoords.sql')

        def read_floats(index):
            return numpy.fromstring(input_row[index].read(), '>f').astype('d')

        newCoords = None

        sql = self.get_sql('ZonationCoords.sql')
        records = self.db.execute(sql, well_id=wellId, zonation_id=zoneDef[1], zone_id=zoneDef[0])

        if records is not None:
            for input_row in records:
                x = read_floats(12)
                y = read_floats(13)
                md = read_floats(14)
                tvd = read_floats(15)

                depth = input_row[4]
                lon = input_row[10]
                lat = input_row[11]

                pt = QgsPoint(lon, lat)
                if self.xform:
                    pt = self.xform.transform(pt)

                newCoords = self._calcOffset(pt.x(), pt.y(), x, y, md, tvd, depth)

        return newCoords


    def _calcOffset(self, lon, lat, x, y, md, tvd, depth):
        jp = None
        lastIdx = len(x) - 1
        for ip in xrange(len(x) - 1):
            if md[ip] <= depth <= md[ip + 1]:
                jp = ip

        xPosition = 0
        yPosition = 0
        if jp is not None:
            rinterp = (depth - md[jp]) / (md[jp + 1] - md[jp])
            xPosition = x[jp] + rinterp * (x[jp + 1] - x[jp])
            yPosition = y[jp] + rinterp * (y[jp + 1] - y[jp])
        elif depth >= md[lastIdx]:
            xPosition = x[lastIdx]
            yPosition = y[lastIdx]

        # newCoords = self.lon_lat_add(lon, lat, xPosition, yPosition)
        newCoords = QgsPoint(lon+xPosition, lat+yPosition)

        return newCoords

    def lon_lat_add(self, lon, lat, x, y):
        meterCrs = QgsCoordinateReferenceSystem()
        meterCrs.createFromProj4('+proj=tmerc +lon_0={} +k=1 +x_0=0 +y_0=0 +ellps=WGS84 +datum=WGS84 +units=m +no_defs'.format(lon))
        geoCrs = QgsCoordinateReferenceSystem('epsg:4326')

        toMeters = QgsCoordinateTransform(geoCrs, meterCrs)
        toGeo = QgsCoordinateTransform(meterCrs, geoCrs)

        geoPt = QgsPoint(lon, lat)
        mPt = toMeters.transform(geoPt)

        return toGeo.transform(QgsPoint(mPt.x()+x, mPt.y()+y))


    def fillZonations(self):
        sqlFile = os.path.join(self.plugin_dir, 'db', 'ZonationParams_zonation.sql')
        if os.path.exists(sqlFile):
            f = open(sqlFile, 'r')
            sql = f.read()
            f.close()

            records = self.db.execute(sql)

            scrollToItem = None
            for id,desc in records:
                item = QListWidgetItem(to_unicode(desc))
                item.setData(Qt.UserRole, id)
                self.zonationListWidget.addItem(item)

                if id in self.selectedZonations:
                    item.setSelected(True)
                    if scrollToItem is None:
                        scrollToItem = item

            self.zonationListWidget.scrollToItem(scrollToItem)

        return


    def _fillZones(self, zonationId):
        sqlFile = os.path.join(self.plugin_dir, 'db', 'ZonationParams_zone.sql')
        if os.path.exists(sqlFile):
            f = open(sqlFile, 'r')
            sql = f.read()
            f.close()

            records = self.db.execute(sql, zonation_id=zonationId)

            scrollToItem = None
            for id,desc in records:
                item = QListWidgetItem(to_unicode(desc))
                item.setData(Qt.UserRole, [id, zonationId])
                self.zoneListWidget.addItem(item)

                if id in self.selectedZones:
                    item.setSelected(True)
                    if scrollToItem is None:
                        scrollToItem = item

            self.zoneListWidget.scrollToItem(scrollToItem)

        return

    def mParamToolButton_clicked(self):
        pass