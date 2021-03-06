# -*- coding: utf-8 -*-

import os

from qgis.core import *
from qgis.gui import QgsMessageBar
from PyQt4 import QtGui, uic
from PyQt4.QtGui import *
from PyQt4.QtCore import *
from collections import namedtuple

from os.path import abspath
import json
import ast

from db import Oracle, Sqlite
from QgisPDS.connections import create_connection
from utils import *
from bblInit import *
from tig_projection import *
import time
import sys


IS_DEBUG=False
IS_PROFILING=False

class BBL_LIFT_METHOD:
    def __init__(self, code, isFlowing, isPump):
        self.code = code
        self.isFlowing = isFlowing
        self.isPump = isPump

    @property
    def code(self):
        return self.code
    
    @property
    def isFlowing(self):
        return self.isFlowing

    @property
    def isPump(self):
        return self.isPump 




FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'qgis_pds_production_base.ui'))
    
class QgisPDSProductionDialog(QtGui.QDialog, FORM_CLASS):

    #===========================================================================
    # 
    #===========================================================================
    @property
    def db(self):
        if self._db is None:
            QtGui.QMessageBox.critical(None, self.tr(u'Error'), self.tr(u'No current PDS project'), QtGui.QMessageBox.Ok)            
        else:
            return self._db
    @db.setter
    def db(self,val):
        self._db=val

    #===========================================================================
    # 
    #===========================================================================
    def __init__(self, project, iface, isCP=True, _layer=None, parent=None):
        """Constructor."""
        super(QgisPDSProductionDialog, self).__init__(parent)       
        
        self.setupUi(self)

        if not isCP:
            self.setWindowTitle(self.tr("Map of cumulative production"))

        self.initialised = False
        self.layer = _layer
        self._db = None

        self.reservoirsListWidget.setEnabled(self.layer is None)
        
        self.attrWellId =       u'well_id'
        self.attrLatitude =     u'latitude'
        self.attrLongitude =    u'longitude'
        self.attrDays =         u'days'
        self.attrSymbolId =     u'symbolid'
        self.attrSymbol =       u'symbolcode'
        self.attrSymbolName =   u'symbolname'
        self.attrWellRole =     u'wellrole'
        self.attrWellStatus =   u'wellstatus'
        self.attrWellStatusReason =   u'wsreason'
        self.attrWellStatusInfo =     u'wsinfo'
        self.attrLiftMethod =   u'liftmethod'
        self.attr_lablx =       u"lablx"
        self.attr_lably =       u"lably"
        self.attr_labloffx =    u"labloffx"
        self.attr_labloffy =    u"labloffy"
        self.attr_labloffset =  u"labloffset"
        self.attr_lablwidth =   u"lablwidth"
        self.attr_bubblesize =  u"bubblesize"
        self.attr_bubblefields = OLD_NEW_FIELDNAMES[1] #"bubblefields"
        self.attr_scaletype =   u"scaletype"
        self.attr_movingres =   u"movingres"
        self.attr_resstate =    u"resstate"
        self.attr_multiprod =   u"multiprod"
        self.attr_labels =      u'bbllabels'
        self.attr_startDate =   u'startdate'

        self.dateFormat = u'dd/MM/yyyy HH:mm:ss'

        self.iface = iface
        self.project = project
        self.isCurrentProd = isCP
        if self.project is None:
            QtGui.QMessageBox.critical(None, self.tr(u'Error'), self.tr(u'No current PDS project'), QtGui.QMessageBox.Ok)
            return
        else:
            self.setWindowTitle(self.windowTitle() + ' - ' + self.tr(u'project: {0}').format(self.project['project']))
            
        self.mSelectedReservoirs = []
        self.mPhaseFilter = []
        self.mProductionWells = []
        self.mWells = {}
        self.reservoirNumbers = []
        self.reservoirIds = []
        
        self.readSettings()

        if self.layer:
            self.mSelectedReservoirs = ast.literal_eval(self.layer.customProperty("pds_prod_SelectedReservoirs"))
        
        self.endDateEdit.setDateTime(self.mEndDate)
        self.startDateEdit.setDateTime(self.mStartDate)

        self.mDynamicCheckBox.setEnabled(self.isCurrentProd)
        self.startDateEdit.setEnabled(not self.isCurrentProd or (self.isCurrentProd and self.mDynamicCheckBox.isChecked()) )
        self.firstDate.setEnabled(not self.isCurrentProd or (self.isCurrentProd and self.mDynamicCheckBox.isChecked()))

        self._getProjection()

        self.readReservoirOrders()

        reservoirs = self._getReservoirs()
        self.reservoirs = []
        if reservoirs is not None:
            for reservoir_part_code in reservoirs:
                reservoirName = to_unicode("".join(reservoir_part_code))
                self.reservoirs.append(NAMES(name=reservoirName, selected=True))
                item = QtGui.QListWidgetItem(reservoirName)
                isSelected = item.text() in self.mSelectedReservoirs
                if self.reservoirsListWidget.isEnabled():
                    self.reservoirsListWidget.addItem(item)
                    self.reservoirsListWidget.setItemSelected(item, isSelected)
                elif isSelected:
                    self.reservoirsListWidget.addItem(item)


        self.realEndDate = QDate()
        self.realStartDate = QDate()
        self.bbl_getproduction_period(False)

        self.initialised = True
    #===========================================================================
    # 
    #===========================================================================
    def _getProjection(self):
        self.proj4String = 'epsg:4326'
        connection = create_connection(self.project)
        scheme = self.project['project']
        try:
            self.db = connection.get_db(scheme)
            self.tig_projections = TigProjections(db=self.db)
            proj = self.tig_projections.get_projection(self.tig_projections.default_projection_id)
            if proj is not None:
                self.proj4String = 'PROJ4:'+proj.qgis_string
                destSrc = QgsCoordinateReferenceSystem()
                destSrc.createFromProj4(proj.qgis_string)
                sourceCrs = QgsCoordinateReferenceSystem('epsg:4326')
                self.xform = QgsCoordinateTransform(sourceCrs, destSrc)
        except Exception as e:
            QgsMessageLog.logMessage(u"Project projection read error {0}: {1}".format(scheme, str(e)), tag="QgisPDS.Error")
            self.iface.messageBar().pushMessage(self.tr("Error"),
                                                self.tr(u'Project projection read error {0}: {1}').format(
                                                scheme, str(e)),
                                                level=QgsMessageBar.CRITICAL)
            return
        
    #===========================================================================
    # read reservoirs names from DB
    #===========================================================================
    def _getReservoirs(self):
        connection = create_connection(self.project)
        scheme = self.project['project']
        try:           
            self.db = connection.get_db(scheme)
            result = self.db.execute("select reservoir_part_code from reservoir_part where  entity_type_nm = 'RESERVOIR_ZONE'")
            # db.disconnect()
            return result
        except Exception as e:
            QgsMessageLog.logMessage(u"Project production read error {0}: {1}".format(scheme, str(e)), tag="QgisPDS.Error")
            self.iface.messageBar().pushMessage(self.tr("Error"), 
                self.tr(u'Read production from project {0}: {1}').format(scheme, str(e)), level=QgsMessageBar.CRITICAL)
            return None
    #===========================================================================
    # 
    #===========================================================================
    def readReservoirOrders(self):
        sql = ("select reservoir_part.reservoir_part_code, "
            " p_equipment_fcl.string_value "
            " from p_equipment_fcl, equipment_insl, "
            " reservoir_part "
            "where reservoir_part.entity_type_nm = 'RESERVOIR_ZONE' "
            " and equipment_insl.equipment_item_s = p_equipment_fcl.object_s "
            " and reservoir_part.reservoir_part_s = equipment_insl.facility_s "
            " and p_equipment_fcl.bsasc_source = 'order no'")

        IS_DEBUG and QgsMessageLog.logMessage(u"Execute readReservoirOrders: {}\\n\n".format(sql), tag="QgisPDS.sql")
        result = self.db.execute(sql)
        if result is not None:
            for reservoirId, reservoirNumber in result:
                self.reservoirNumbers.append(reservoirNumber)
                self.reservoirIds.append(reservoirId)

    #===========================================================================
    # 
    #===========================================================================
    def getReservoirOrder(self, reservoir):
        if reservoir in self.reservoirIds:
            idx = self.reservoirIds.index(reservoir)
            if idx is not None:
                return self.reservoirNumbers[idx]
        return 0

    #===========================================================================
    # 
    #===========================================================================
    def isLower(self, reservoirs1, reservoirs2):
        for name1 in reservoirs1:
            if name1.selected:
                for name2 in reservoirs2:
                    if name2.selected and self.getReservoirOrder(name1.name)<=self.getReservoirOrder(name2.name):
                        return False
        return True

    #===========================================================================
    # 
    #===========================================================================
    def isUpper(self, reservoirs1, reservoirs2):
        for name1 in reservoirs1:
            if name1.selected:
                for name2 in reservoirs2:
                    if name2.selected and self.getReservoirOrder(name1.name)>=self.getReservoirOrder(name2.name):
                        return False
        return True

    #===========================================================================
    # 
    #===========================================================================
    def intersectReservoirs(self, reservoirs1, reservoirs2):
        res = []
        for name1 in reservoirs1:
            if name1.selected:
                for name2 in reservoirs2:
                    if name2.selected and name1.name == name2.name:
                        res.append(NAMES(name=name1.name, selected=True))

        return res

    #===========================================================================
    # 
    #===========================================================================
    def subtractReservoirs(self, reservoirs1, reservoirs2):
        res = []
        for name1 in reservoirs1:
            if name1.selected:
                f = False
                for name2 in reservoirs2:
                    if name2.selected and name1.name == name2.name:
                        f = True
                        break

                if not f:
                    res.append(NAMES(name=name1.name, selected=True))

        return res

    #===========================================================================
    # 
    #===========================================================================
    def isEqualReservoirs(self, reservoirs1, reservoirs2):
        res1 = self.subtractReservoirs(reservoirs1, reservoirs2)
        res2 = self.subtractReservoirs(reservoirs2, reservoirs1)
        return len(res1) == 0 and len(res2) == 0

    #===========================================================================
    # 
    #===========================================================================
    def on_buttonBox_accepted(self):
        if IS_DEBUG or IS_PROFILING:
            import cProfile
            _profiler = cProfile.Profile()
            _profiler.enable()
        #
        self.createProductionLayer()
        #
        if IS_DEBUG or IS_PROFILING:
            import pstats, io
            from os.path import expanduser
            home = expanduser("~")            
            _profiler.disable()
            s = open(os.path.join(home,'qgispds.prof.log'), 'a')
            ps=pstats.Stats(_profiler, stream=s).strip_dirs().sort_stats('cumulative').print_stats()
            s = open(os.path.join(home,'qgispds.prof.log'), 'r')            
            QgsMessageLog.logMessage(u"profile: \n{}".format(''.join(s.readlines())), tag="QgisPDS.profile")

        

    #===========================================================================
    # 
    #===========================================================================
    def isInitialised(self):
        return self.initialised

    #===========================================================================
    # 
    #===========================================================================
    def diagrammTypeChanged(self, index):
        if index < 0:
            return

        code = self.diagrammType.itemData(index)
        diagramm = bblInit.standardDiagramms[code]

        vec = diagramm.fluids
        for idx, v in enumerate(vec):
            self.fluidsListWidget.item(idx).setSelected(v)

    #===========================================================================
    # 
    #===========================================================================
    def createProductionLayer(self):
        self.mEndDate = self.endDateEdit.dateTime()
        self.mStartDate = self.startDateEdit.dateTime()

        if self.layer is None:
            self.mSelectedReservoirs = self.getSelectedReservoirs()
            self.mPhaseFilter = self.getSelectedFluids()

            self.uri = "Point?crs={}".format(self.proj4String)
            self.uri += '&field={}:{}'.format(self.attrWellId,      "string" )
            self.uri += '&field={}:{}'.format(self.attrLatitude,    "double" )
            self.uri += '&field={}:{}'.format(self.attrLongitude,   "double" )
            self.uri += '&field={}:{}'.format(self.attrSymbolId,    "string" )
            self.uri += '&field={}:{}'.format(self.attrSymbolName,  "string" )
            self.uri += '&field={}:{}'.format(self.attrSymbol,      "integer")
            self.uri += '&field={}:{}'.format(self.attrWellRole,    "string" )
            self.uri += '&field={}:{}'.format(self.attrWellStatus,  "string" )
            self.uri += '&field={}:{}'.format(self.attrWellStatusReason,  "string" )
            self.uri += '&field={}:{}'.format(self.attrWellStatusInfo  ,  "string" )
            self.uri += '&field={}:{}'.format(self.attr_startDate,  "date"   )
            self.uri += '&field={}:{}'.format(self.attrDays,        "double" )
            self.uri += '&field={}:{}'.format(self.attrLiftMethod,  "string" )
            self.uri += '&field={}:{}'.format(self.attr_lablx,      "double" )
            self.uri += '&field={}:{}'.format(self.attr_lably,      "double" )
            self.uri += '&field={}:{}'.format(self.attr_labloffx,   "double" )
            self.uri += '&field={}:{}'.format(self.attr_labloffy,   "double" )
            self.uri += '&field={}:{}'.format(self.attr_labloffset, "double" )
            self.uri += '&field={}:{}'.format(self.attr_lablwidth,  "double" )
            self.uri += '&field={}:{}'.format(self.attr_bubblesize, "double" )
            # self.uri += '&field={}:{}'.format(self.attr_bubblefields, "string")
            self.uri += '&field={}:{}'.format(self.attr_scaletype,  "string" )
            self.uri += '&field={}:{}'.format(self.attr_movingres,  "string" )
            self.uri += '&field={}:{}'.format(self.attr_resstate,   "string" )
            self.uri += '&field={}:{}'.format(self.attr_multiprod,  "string" )
            # self.uri += '&field={}:{}'.format(self.attr_labels, "string")
            for fl in bblInit.fluidCodes:
                self.uri += '&field={}:{}'.format(bblInit.attrFluidVolume(          fl.code), "double" )
                self.uri += '&field={}:{}'.format(bblInit.attrFluidMass(            fl.code), "double" )
                self.uri += '&field={}:{}'.format(bblInit.attrFluidMaxDebitMass(    fl.code), "double" )
                self.uri += '&field={}:{}'.format(bblInit.attrFluidMaxDebitDateMass(fl.code), "date"   )
                self.uri += '&field={}:{}'.format(bblInit.attrFluidMaxDebitVol(     fl.code), "double" )
                self.uri += '&field={}:{}'.format(bblInit.attrFluidMaxDebitDateVol( fl.code), "date"   )
            layerName = u"Current production - " + ",".join(self.mSelectedReservoirs)
            if not self.isCurrentProd:
                layerName = u"Cumulative production - " + ",".join(self.mSelectedReservoirs)
            elif self.mDynamicCheckBox.isChecked():
                layerName = u"Dynamic production - " + ",".join(self.mSelectedReservoirs)
            #layerName=layerName[:220] #max f_name size
            #layerName=u"kurovdag_m2_Cumulative production - PS01_zeh3,AP02_2_z2,Iob-AP02_z1, PS01_z2,IIa-AP02_z1,PS02z1,IIb-AP02_z1,IIb1-AP02_z1,IIc-AP02_z1,IIc1-AP02_z1,IIc2_AP02_z1,IIc3-AP02_z1,IIc4-AP02_z1,IId-AP02_z1,IIe-AP02_z1,IIob12.shp"
            self.layer = QgsVectorLayer(self.uri, layerName, "memory")
            if self.layer is None:
                QtGui.QMessageBox.critical(None, self.tr(u'Error'), self.tr(u'Layer create error'), QtGui.QMessageBox.Ok)
                return
            self.layer = memoryToShp(self.layer, self.project['project'], layerName)
            if self.isCurrentProd:
                self.layer.setCustomProperty("qgis_pds_type", "pds_current_production")
            else:
                self.layer.setCustomProperty("qgis_pds_type", "pds_cumulative_production")
            self.layer.setCustomProperty("pds_project",                 str(self.project)                      )
            self.layer.setCustomProperty("pds_prod_endDate",            self.mEndDate.toString(self.dateFormat))
            self.layer.setCustomProperty("pds_prod_SelectedReservoirs", str(self.mSelectedReservoirs)          )
            self.layer.setCustomProperty("pds_prod_PhaseFilter",        str(self.mPhaseFilter)                 )

            # symbolList = self.layer.rendererV2().symbols()
            # symbol = QgsSymbolV2.defaultSymbol(self.layer.geometryType())

            registry = QgsSymbolLayerV2Registry.instance()
            
            # marker = QgsMarkerSymbolV2()
            #
            # bubbleMeta = registry.symbolLayerMetadata('BubbleMarker')
            # if bubbleMeta is not None:
            #     bubbleLayer = bubbleMeta.createSymbolLayer({})
            #     marker.changeSymbolLayer(0, bubbleLayer)
            #     renderer = QgsSingleSymbolRendererV2(marker)
            #     self.layer.setRendererV2(renderer)
            
            palyr = QgsPalLayerSettings()
            palyr.readFromLayer(self.layer)
            palyr.enabled = True
            palyr.fieldName = self.attrWellId
            palyr.placement= QgsPalLayerSettings.OverPoint
            palyr.quadOffset = QgsPalLayerSettings.QuadrantAboveRight
            palyr.labelOffsetInMapUnits = False
            palyr.distInMapUnits = True
            palyr.displayAll = True
            palyr.textColor = QtGui.QColor(255,0,0)
            palyr.fontSizeInMapUnits = False
            palyr.textFont.setPointSizeF(7)

            palyr.setDataDefinedProperty(QgsPalLayerSettings.PositionX,True,False,'', self.attr_lablx)
            palyr.setDataDefinedProperty(QgsPalLayerSettings.PositionY,True,False,'', self.attr_lably)
            palyr.setDataDefinedProperty(QgsPalLayerSettings.OffsetXY, True, True, 'format(\'%1,%2\', "labloffx" , "labloffy")', '')
            palyr.writeToLayer(self.layer)
            
            #---load user styles
            load_styles_from_dir(layer=self.layer, styles_dir=os.path.join(plugin_path() ,STYLE_DIR, USER_PROD_STYLE_DIR) ,switchActiveStyle=False)
            #---load default style
            load_style(layer=self.layer, style_path=os.path.join(plugin_path() ,STYLE_DIR ,PROD_STYLE+".qml"))
        else:
            bblInit.checkFieldExists(self.layer, self.attr_startDate, QVariant.Date, 50, 0)
            bblInit.updateOldProductionStructure(self.layer)
        self.loadProductionLayer(self.layer)
        QgsMapLayerRegistry.instance().addMapLayer(self.layer)
        bblInit.setAliases(self.layer)
        self.writeSettings()
    #===========================================================================
    # 
    #===========================================================================
    def getLayer(self):
        return self.layer
    #===========================================================================
    # 
    #===========================================================================
    def loadProductionLayer(self, layer):
        self.layer = layer

        # prjStr = layer.customProperty("pds_project")
        # self.project = ast.literal_eval(prjStr)

        if self.project is None:
            QtGui.QMessageBox.critical(None, self.tr(u'Error'), self.tr(u'No current PDS project'), QtGui.QMessageBox.Ok)
            return
        else:
            self.iface.messageBar().pushMessage(self.tr(u'Current PDS project: {0}').format(self.project['project']), duration=10)

    #try:
        # self.mEndDate = QDateTime.fromString(layer.customProperty("pds_prod_endDate"), self.dateFormat)
        self.mSelectedReservoirs = ast.literal_eval(layer.customProperty("pds_prod_SelectedReservoirs"))
        self.mPhaseFilter =        ast.literal_eval(layer.customProperty("pds_prod_PhaseFilter")       )
        self.mProductionWells = []
        self.mWells = {}
    
        connection = create_connection(self.project)
        scheme = self.project['project']
        self.db = connection.get_db(scheme)


        self.mSelectedReservoirsText = self.getReservoirsFilter()

        self.mEndDate.setDate(QDate(self.mEndDate.date().year(), self.mEndDate.date().month(), self.mEndDate.date().daysInMonth()))
        if self.isCurrentProd and not self.mDynamicCheckBox.isChecked():
            self.mStartDate.setDate(QDate(self.mEndDate.date().year(), self.mEndDate.date().month(), 1))
        else:
            self.mStartDate.setDate(QDate(self.mStartDate.date().year(), self.mStartDate.date().month(), 1))

        if self.mDynamicCheckBox.isChecked() and self.isCurrentProd:
            # progressMessageBar = self.iface.messageBar()
            # self.progress = QProgressBar()
            # self.progress.setMaximum(100)
            # progressMessageBar.pushWidget(self.progress)

            self.getWells(self.mSelectedReservoirsText)
            self.readDynamicProduction()

            # saveProductionWells = list(self.mProductionWells)
            # saveWells = dict(self.mWells)
            #
            # tmpStartDate = self.startDateEdit.dateTime()
            #
            # saveStartDate = QDateTime(tmpStartDate)
            # saveEndDate = QDateTime(self.mEndDate)
            #
            # curDate = self.mEndDate
            # daysTo = tmpStartDate.daysTo(curDate)
            # curDays = 0
            # # try:
            # while curDate > tmpStartDate:
            #     self.mEndDate.setDate(QDate(curDate.date().year(), curDate.date().month(), curDate.date().daysInMonth()))
            #     self.mStartDate.setDate(QDate(curDate.date().year(), curDate.date().month(), 1))
            #
            #     self.mProductionWells = list(saveProductionWells)
            #     print self.mProductionWells
            #     self.mWells = dict(saveWells)
            #     self.readProduction()
            #
            #     curDays += curDate.date().daysInMonth()
            #     self.progress.setValue(100 * curDays / daysTo)
            #     QCoreApplication.processEvents()
            #
            #     curDate = curDate.addMonths(-1)
            # # except:
            # #     pass
            #
            # self.mStartDate = QDateTime(saveStartDate)
            # self.mEndDate = QDateTime(saveEndDate)
            #
            # self.iface.messageBar().clearWidgets()
        else:
            self.getWells(self.mSelectedReservoirsText)
            self.readProduction()

        self.db.disconnect()

        self.layer.updateExtents()

    # except Exception as e:
        #self.iface.messageBar().pushMessage(self.tr("Error"), self.tr(str(e)), level=QgsMessageBar.CRITICAL)
     
        
    #===========================================================================
    # Create production layer
    #===========================================================================
    def readProduction(self):
        time_start = time.time()
        
        self.mPhaseFilterText = ""
        
        if len(self.mSelectedReservoirs) < 1:
            QtGui.QMessageBox.critical(None, self.tr(u'Error'), self.tr(u'Reservoir is not selected'), QtGui.QMessageBox.Ok)
            return
    
        self.productions = self.layer.dataProvider()     
        
        # self.mEndDate.setDate(QDate(self.mEndDate.date().year(), self.mEndDate.date().month(), self.mEndDate.date().daysInMonth()))
        # if self.isCurrentProd:
        #     self.mStartDate.setDate(QDate(self.mEndDate.date().year(), self.mEndDate.date().month(), 1))
        # else:
        #     self.mStartDate.setDate(QDate(self.mStartDate.date().year(), self.mStartDate.date().month(), 1))
        #
        # self.mSelectedReservoirsText = self.getReservoirsFilter()
        # self.getWells(self.mSelectedReservoirsText)

        IS_DEBUG and QgsMessageLog.logMessage(u"prod config read in  in {}".format((time.time() - time_start)/60), tag="QgisPDS.readProduction")
        time_start=time.time()
        
        IS_DEBUG and QgsMessageLog.logMessage(u"read production for wells {}".format(lambda v:v.name,self.mProductionWells), tag="QgisPDS.readProduction")
        self.readWellsProduction(self.mProductionWells)
        IS_DEBUG and QgsMessageLog.logMessage(u"prod read in  in {}".format((time.time() - time_start)/60), tag="QgisPDS.readProduction")
        time_start=time.time()

        for pdw in self.mProductionWells:
            self.calcBubbles(pdw)
        IS_DEBUG and QgsMessageLog.logMessage(u"bubble calculated in  in {}".format((time.time() - time_start)/60), tag="QgisPDS.readProduction")
        time_start=time.time()

        liftMethodIdx = self.layer.fieldNameIndex(self.attrLiftMethod)

        self._readAllWells()
        IS_DEBUG and QgsMessageLog.logMessage(u"well read in  in {}".format((time.time() - time_start)/60), tag="QgisPDS.readProduction")
        time_start=time.time()

        is_refreshed =   False                                      #--- id that layer have refreshed records
        is_layerfiltered=len(self.layer.subsetString().strip())>1 #--- if layer with filter provider allowed only update production/coordinates.
        is_needupdcoord= self.mUpdateWellLocation.isChecked()
        is_needaddall=   self.mAddAllWells.isChecked()
        is_rowwithprod=  lambda feature:feature.attribute(self.attrSymbol)!=71
        IS_DEBUG and QgsMessageLog.logMessage("is_layerfiltered={};is_needupdcoord={};is_needaddall={};".format(is_layerfiltered,is_needupdcoord,is_needaddall), tag="QgisPDS.readProduction")
        #Refresh or add feature
        if self.layer.isEditable(): self.layer.commitChanges()
        with edit_layer(self.layer):
            ############################
            ####### TEST BLOCK
            ############################
            cDays      =        self.layer.fieldNameIndex(self.attrDays             )
            cSymbol    =        self.layer.fieldNameIndex(self.attrSymbol           )
            cSymbolId  =        self.layer.fieldNameIndex(self.attrSymbolId         )
            cSymbolName=        self.layer.fieldNameIndex(self.attrSymbolName       )
            cResState  =        self.layer.fieldNameIndex(self.attr_resstate        )
            cMovingRes =        self.layer.fieldNameIndex(self.attr_movingres       )
            cMultiProd =        self.layer.fieldNameIndex(self.attr_multiprod       )
            cStartDate =        self.layer.fieldNameIndex(self.attr_startDate       )
            cRole      =        self.layer.fieldNameIndex(self.attrWellRole         )
            cStatus    =        self.layer.fieldNameIndex(self.attrWellStatus       )
            cStatusReason    =  self.layer.fieldNameIndex(self.attrWellStatusReason )
            cStatusInfo       = self.layer.fieldNameIndex(self.attrWellStatusInfo   )            
            attr_2_upd=[  ###old column             old_col_id       new_col    
                         [self.attrDays             ,cDays             ,  self.attrDays              ]
                        ,[self.attrSymbol           ,cSymbol           ,  self.attrSymbol            ]
                        ,[self.attrSymbolId         ,cSymbolId         ,  self.attrSymbolId          ]
                        ,[self.attrSymbolName       ,cSymbolName       ,  self.attrSymbolName        ]
                        ,[self.attr_resstate        ,cResState         ,  self.attr_resstate         ]
                        ,[self.attr_movingres       ,cMovingRes        ,  self.attr_movingres        ]
                        ,[self.attr_multiprod       ,cMultiProd        ,  self.attr_multiprod        ]
                        ,[self.attr_startDate       ,cStartDate        ,  self.attr_startDate        ]
                        ,[self.attrWellRole         ,cRole             ,  self.attrWellRole          ]
                        ,[self.attrWellStatus       ,cStatus           ,  self.attrWellStatus        ]
                        ,[self.attrWellStatusReason ,cStatusReason     ,  self.attrWellStatusReason  ]
                        ,[self.attrWellStatusInfo   ,cStatusInfo       ,  self.attrWellStatusInfo    ]
                        ]
            for feature in self.mWells.values():                                 #--- iterate over each record in result
                args = (self.attrWellId, feature.attribute(self.attrWellId))
                expr = QgsExpression('\"{0}\"=\'{1}\''.format(*args))            #--- search in layer record with that WELL_ID
                searchRes = self.layer.getFeatures(QgsFeatureRequest(expr))
                num = 0
                IS_DEBUG and QgsMessageLog.logMessage(u"update attribute of well {}".format(feature.attribute(self.attrWellId)), tag="QgisPDS.debug")
                for f in searchRes:             #--- iterate over each row in base layer for current well
                    is_refreshed = True
                    #--- update coord if checked
                    if is_needupdcoord:                                 #--- update coord if checked
                        self.layer.changeGeometry(f.id(), feature.geometry())
                    #--- update well attribute
                    for (c_old_name,c_old_idx,c_new_name) in attr_2_upd: #--- update well special attribute @see:'attr_2_upd'
                        if f.attribute(c_old_name)!=feature.attribute(c_new_name):
                            self.layer.changeAttributeValue(f.id(), c_old_idx      , feature.attribute(c_new_name))  #f.setAttribute( c_old       , feature.attribute(c_new) )## ---incorrect, not update feature in layer
                    if liftMethodIdx >= 0:                               #--- update liftmetho id
                        self.layer.changeAttributeValue(f.id(), liftMethodIdx, feature.attribute(self.attrLiftMethod))
                    for fl in bblInit.fluidCodes:                        #--- update production attributes
                        attrMass             = bblInit.attrFluidMass(             fl.code)
                        attrVol              = bblInit.attrFluidVolume(           fl.code)
                        attrMaxDebitMass     = bblInit.attrFluidMaxDebitMass(     fl.code)
                        attrMaxDebitVol      = bblInit.attrFluidMaxDebitVol(      fl.code)
                        attrMaxDebitMass     = bblInit.attrFluidMaxDebitMass(     fl.code)
                        attrMaxDebitDateMass = bblInit.attrFluidMaxDebitDateMass( fl.code)
                        attrMaxDebitDateVol  = bblInit.attrFluidMaxDebitDateVol(  fl.code)
                        self.layer.changeAttributeValue(f.id(), self.layer.fieldNameIndex(attrMass),             feature.attribute(attrMass)            )
                        self.layer.changeAttributeValue(f.id(), self.layer.fieldNameIndex(attrVol),              feature.attribute(attrVol)             )
                        self.layer.changeAttributeValue(f.id(), self.layer.fieldNameIndex(attrMaxDebitMass),     feature.attribute(attrMaxDebitMass)    )
                        self.layer.changeAttributeValue(f.id(), self.layer.fieldNameIndex(attrMaxDebitVol),      feature.attribute(attrMaxDebitVol)     )
                        self.layer.changeAttributeValue(f.id(), self.layer.fieldNameIndex(attrMaxDebitDateMass), feature.attribute(attrMaxDebitDateMass))
                        self.layer.changeAttributeValue(f.id(), self.layer.fieldNameIndex(attrMaxDebitDateVol),  feature.attribute(attrMaxDebitDateVol) )
                    num +=1
                #--- add new well if need
                if not num:                 #--- well not present in base layer
                    if not is_layerfiltered:  #--- if layer without filter provider,than allow add new records
                        if is_needaddall or is_rowwithprod(feature):       #--- Add All wells checked or new row have production
                            self.layer.addFeatures([feature])
                    else:
                        pass
                self.layer.commitChanges()  #--- commit each row
                self.layer.startEditing()   #--- and start edit again

        #--- if layer filtered and selected Add All remove filter,add all,set back filter
        if is_layerfiltered and is_needaddall:
            with edit_layer(self.layer):
                for feature in self.mWells.values(): 
                    args = (self.attrWellId, feature.attribute(self.attrWellId))
                    expr = QgsExpression('\"{0}\"=\'{1}\''.format(*args))            #--- search in base layer record with that WELL_ID
                    searchRes = self.layer.getFeatures(QgsFeatureRequest(expr))
                    for f in searchRes:
                        break
                    else:
                        self.layer.addFeatures([feature])
                        self.layer.commitChanges()  #--- commit each row
                        self.layer.startEditing()   #--- and start edit again

        IS_DEBUG and QgsMessageLog.logMessage(u"atr updated in  in {}".format((time.time() - time_start)/60), tag="QgisPDS.readProduction")
        time_start=time.time()
                    
        # if is_refreshed:
        #     self.iface.messageBar().pushMessage(self.tr(u'Layer: {0} refreshed').format(self.layer.name()), duration=4)
        self.writeSettings()

    #===========================================================================
    # 
    #===========================================================================
    def updateFeature(self, feature, prod):
        feature.setAttribute(self.attrDays, prod.days)
        feature.setAttribute(self.attr_startDate, prod.stadat.date())

        for i, fl in enumerate(bblInit.fluidCodes):
            feature.setAttribute(bblInit.attrFluidMass(fl.code), prod.massVals[i])
            feature.setAttribute(bblInit.attrFluidVolume(fl.code), prod.volumeVals[i])


  # ===========================================================================
    # Create production layer
    # ===========================================================================
    def readDynamicProduction(self):
        time_start = time.time()

        self.mPhaseFilterText = ""

        if len(self.mSelectedReservoirs) < 1:
            QtGui.QMessageBox.critical(None, self.tr(u'Error'), self.tr(u'Reservoir is not selected'),
                                       QtGui.QMessageBox.Ok)
            return

        self.productions = self.layer.dataProvider()
        self.readWellsProduction(self.mProductionWells)
        #for pdw in self.mProductionWells:    self.readWellProduction(pdw)

        is_refreshed = False  # --- id that layer have refreshed records
        is_layerfiltered = len(self.layer.subsetString().strip()) > 1  # --- if layer with filter provider allowed only update production/coordinates.
        is_needupdcoord = self.mUpdateWellLocation.isChecked()
        is_needaddall = self.mAddAllWells.isChecked()
        is_rowwithprod = lambda feature: feature.attribute(self.attrSymbol) != 71

        # Refresh or add feature
        if self.layer.isEditable(): self.layer.commitChanges()
        with edit_layer(self.layer):
            ############################
            ####### TEST BLOCK
            ############################
            cDays =             self.layer.fieldNameIndex(self.attrDays             )
            cSymbol =           self.layer.fieldNameIndex(self.attrSymbol           )
            cSymbolId =         self.layer.fieldNameIndex(self.attrSymbolId         )
            cSymbolName =       self.layer.fieldNameIndex(self.attrSymbolName       )
            cResState =         self.layer.fieldNameIndex(self.attr_resstate        )
            cMovingRes =        self.layer.fieldNameIndex(self.attr_movingres       )
            cMultiProd =        self.layer.fieldNameIndex(self.attr_multiprod       )
            cStartDate =        self.layer.fieldNameIndex(self.attr_startDate       )
            cRole      =        self.layer.fieldNameIndex(self.attrWellRole         )
            cStatus    =        self.layer.fieldNameIndex(self.attrWellStatus       )
            cStatusReason    =  self.layer.fieldNameIndex(self.attrWellStatusReason )
            cStatusInfo       = self.layer.fieldNameIndex(self.attrWellStatusInfo   )            
            
            attr_2_upd = [  ###old column       old_col_id       new_col
                  [self.attrDays,             cDays             ,  self.attrDays              ]
                , [self.attrSymbol,           cSymbol           ,  self.attrSymbol            ]
                , [self.attrSymbolId,         cSymbolId         ,  self.attrSymbolId          ]
                , [self.attrSymbolName,       cSymbolName       ,  self.attrSymbolName        ]
                , [self.attr_resstate,        cResState         ,  self.attr_resstate         ]
                , [self.attr_movingres,       cMovingRes        ,  self.attr_movingres        ]
                , [self.attr_multiprod,       cMultiProd        ,  self.attr_multiprod        ]
                , [self.attr_startDate,       cStartDate        ,  self.attr_startDate        ]
                , [self.attrWellRole   ,      cRole             ,  self.attrWellRole          ]
                , [self.attrWellStatus ,      cStatus           ,  self.attrWellStatus        ]
                , [self.attrWellStatusReason ,cStatusReason     ,  self.attrWellStatusReason  ]
                , [self.attrWellStatusInfo   ,cStatusInfo       ,  self.attrWellStatusInfo    ]
                
            ]
            
            for prodWell in self.mProductionWells:
                oldFeature = self.mWells[prodWell.name]
                for prod in prodWell.prods:
                    feature = QgsFeature(oldFeature)
                    self.updateFeature(feature, prod)
                    dateText = prod.stadat.toString(u'yyyy-MM-dd')
                    args = (self.attrWellId, feature.attribute(self.attrWellId), self.attr_startDate, dateText)
                    exprStr = '\"{0}\"=\'{1}\' and \"{2}\"=to_date(\'{3}\')'.format(*args)
                    num = 0
                    expr = QgsExpression(exprStr)
                    searchRes = self.layer.getFeatures(QgsFeatureRequest(expr))
                    for f in searchRes:  # --- iterate over each row in base layer for current well
                        is_refreshed = True
                        # --- update coord if checked
                        if is_needupdcoord:  # --- update coord if checked
                            self.layer.changeGeometry(f.id(), feature.geometry())
                        # --- update well attribute if changed
                        for (c_old_name, c_old_idx, c_new_name) in attr_2_upd:
                            if f.attribute(c_old_name) != feature.attribute(c_new_name):
                                self.layer.changeAttributeValue(f.id(), c_old_idx, feature.attribute(c_new_name))
                    
                        for fl in bblInit.fluidCodes:  # --- update production attributes
                            attrMass = bblInit.attrFluidMass(fl.code)
                            attrVol = bblInit.attrFluidVolume(fl.code)
                    
                            self.layer.changeAttributeValue(f.id(), self.layer.fieldNameIndex(attrMass),
                                                            feature.attribute(attrMass))
                            self.layer.changeAttributeValue(f.id(), self.layer.fieldNameIndex(attrVol),
                                                            feature.attribute(attrVol))
                    
                        num += 1
                    # --- add new well if need
                    if not num:  # --- well not present in base layer
                        if not is_layerfiltered:  # --- if layer without filter provider,than allow add new records
                            if is_needaddall or is_rowwithprod(feature):  # --- Add All wells checked or new row have production
                                self.layer.addFeatures([feature])
                        else:
                            pass
                    self.layer.commitChanges()  # --- commit each row
                    self.layer.startEditing()  # --- and start edit again

        # --- if layer filtered and selected Add All remove filter,add all,set back filter
        if is_layerfiltered and is_needaddall:
            with edit_layer(self.layer):
                for feature in self.mWells.values():
                    args = (self.attrWellId, feature.attribute(self.attrWellId))
                    expr = QgsExpression('\"{0}\"=\'{1}\''.format(*args))  # --- search in base layer record with that WELL_ID
                    searchRes = self.layer.getFeatures(QgsFeatureRequest(expr))
                    for f in searchRes:
                        break
                    else:
                        self.layer.addFeatures([feature])
                        self.layer.commitChanges()  # --- commit each row
                        self.layer.startEditing()  # --- and start edit again

        self.writeSettings()

    # ===========================================================================
    # Create production layer
    # ===========================================================================
    def readDynamicProduction_bck(self):
        time_start = time.time()

        self.mPhaseFilterText = ""

        if len(self.mSelectedReservoirs) < 1:
            QtGui.QMessageBox.critical(None, self.tr(u'Error'), self.tr(u'Reservoir is not selected'),
                                       QtGui.QMessageBox.Ok)
            return

        self.productions = self.layer.dataProvider()

        self.readWellsProduction(self.mProductionWells)
        #for pdw in self.mProductionWells:     self.readWellProduction(pdw)

        is_refreshed = False  # --- id that layer have refreshed records
        is_layerfiltered = len(self.layer.subsetString().strip()) > 1  # --- if layer with filter provider allowed only update production/coordinates.
        is_needupdcoord = self.mUpdateWellLocation.isChecked()
        is_needaddall = self.mAddAllWells.isChecked()
        is_rowwithprod = lambda feature: feature.attribute(self.attrSymbol) != 71

        # Refresh or add feature
        if self.layer.isEditable(): self.layer.commitChanges()
        with edit_layer(self.layer):
            ############################
            ####### TEST BLOCK
            ############################
            cDays =       self.layer.fieldNameIndex(  self.attrDays      )
            cSymbol =     self.layer.fieldNameIndex(  self.attrSymbol    )
            cSymbolId =   self.layer.fieldNameIndex(  self.attrSymbolId  )
            cSymbolName = self.layer.fieldNameIndex(  self.attrSymbolName)
            cResState =   self.layer.fieldNameIndex(  self.attr_resstate )
            cMovingRes =  self.layer.fieldNameIndex(  self.attr_movingres)
            cMultiProd =  self.layer.fieldNameIndex(  self.attr_multiprod)
            cStartDate =  self.layer.fieldNameIndex(  self.attr_startDate)
            cRole      =  self.layer.fieldNameIndex(  self.attrWellRole  )
            cStatus    =  self.layer.fieldNameIndex(  self.attrWellStatus)
            attr_2_upd = [  ###old column       old_col_id       new_col
                  [self.attrDays,       cDays,       self.attrDays        ]
                , [self.attrSymbol,     cSymbol,     self.attrSymbol      ]
                , [self.attrSymbolId,   cSymbolId,   self.attrSymbolId    ]
                , [self.attrSymbolName, cSymbolName, self.attrSymbolName  ]
                , [self.attr_resstate,  cResState,   self.attr_resstate   ]
                , [self.attr_movingres, cMovingRes,  self.attr_movingres  ]
                , [self.attr_multiprod, cMultiProd,  self.attr_multiprod  ]
                , [self.attr_startDate, cStartDate,  self.attr_startDate  ]
                , [self.attrWellRole   ,cRole     ,  self.attrWellRole    ]
                , [self.attrWellStatus ,cStatus   ,  self.attrWellStatus  ]
            ]
            for prodWell in self.mProductionWells:
                oldFeature = self.mWells[prodWell.name]
                for prod in prodWell.prods:
                    feature = QgsFeature(oldFeature)
                    self.updateFeature(feature, prod)
                    dateText = prod.stadat.toString(u'yyyy-MM-dd')
                    args = (self.attrWellId, feature.attribute(self.attrWellId), self.attr_startDate, dateText)
                    exprStr = '\"{0}\"=\'{1}\' and \"{2}\"=to_date(\'{3}\')'.format(*args)
                    expr = QgsExpression(exprStr)
                    searchRes = self.layer.getFeatures(QgsFeatureRequest(expr))
                    num = 0
                    for f in searchRes:  # --- iterate over each row in base layer for current well
                        is_refreshed = True
                        # --- update coord if checked
                        if is_needupdcoord:  # --- update coord if checked
                            self.layer.changeGeometry(f.id(), feature.geometry())
                        # --- update well attribute if changed
                        for (c_old_name, c_old_idx, c_new_name) in attr_2_upd:
                            if f.attribute(c_old_name) != feature.attribute(c_new_name):
                                self.layer.changeAttributeValue(f.id(), c_old_idx, feature.attribute(c_new_name))
                        for fl in bblInit.fluidCodes:  # --- update production attributes
                            attrMass = bblInit.attrFluidMass(   fl.code )
                            attrVol  = bblInit.attrFluidVolume( fl.code )
                            self.layer.changeAttributeValue(f.id(), self.layer.fieldNameIndex(attrMass),
                                                            feature.attribute(attrMass))
                            self.layer.changeAttributeValue(f.id(), self.layer.fieldNameIndex(attrVol),
                                                            feature.attribute(attrVol))
                        num += 1
                    # --- add new well if need
                    if not num:  # --- well not present in base layer
                        if not is_layerfiltered:  # --- if layer without filter provider,than allow add new records
                            if is_needaddall or is_rowwithprod(feature):  # --- Add All wells checked or new row have production
                                self.layer.addFeatures([feature])
                        else:
                            pass
                    self.layer.commitChanges()  # --- commit each row
                    self.layer.startEditing()  # --- and start edit again

        # --- if layer filtered and selected Add All remove filter,add all,set back filter
        if is_layerfiltered and is_needaddall:
            with edit_layer(self.layer):
                for feature in self.mWells.values():
                    args = (self.attrWellId, feature.attribute(self.attrWellId))
                    expr = QgsExpression('\"{0}\"=\'{1}\''.format(*args))  # --- search in base layer record with that WELL_ID
                    searchRes = self.layer.getFeatures(QgsFeatureRequest(expr))
                    for f in searchRes:
                        break
                    else:
                        self.layer.addFeatures([feature])
                        self.layer.commitChanges()  # --- commit each row
                        self.layer.startEditing()  # --- and start edit again
        self.writeSettings()

    #===========================================================================
    # 
    #===========================================================================
    def setWellAttribute(self, name, attr, value):
        feature = self.mWells[name]
        feature.setAttribute(attr, value)
    #===========================================================================
    # 
    #===========================================================================
    def calcProds(self, prod, wellName, sumMass, sumVols):
        if prod.stadat > self.mEndDate or prod.enddat < self.mStartDate: return

        for i, fl in enumerate(bblInit.fluidCodes):
            sumMass[i] = sumMass[i] + prod.massVals[i]
            sumVols[i] = sumVols[i] + prod.volumeVals[i]


        days = prod.days
        if days <= 0:
            days = prod.stadat.daysTo(prod.enddat)
            IS_DEBUG and QgsMessageLog.logMessage( self.tr( u"calcProds: zero time value for well " ) + wellName, self.tr( "QGisPDS" ) )


        if prod.stadat < self.mStartDate:
            days -= prod.stadat.daysTo(self.mStartDate)
        
        if prod.enddat > self.mEndDate:
            days -= self.mEndDate.daysTo(prod.enddat)

        # self.setWellAttribute(wellName, self.attrDays, days)
        return days

    #===========================================================================
    # 
    #===========================================================================
    def calcBubbles(self, prodWell):
        sumMass = [0 for c in bblInit.fluidCodes]
        sumVols = [0 for c in bblInit.fluidCodes]
        sumDays = 0
        for prod in prodWell.prods:
            sumDays = sumDays + self.calcProds(prod, prodWell.name, sumMass, sumVols)

        self.setWellAttribute(prodWell.name, self.attrDays              , sumDays                 )
        self.setWellAttribute(prodWell.name, self.attr_resstate         , prodWell.reservoirState )
        self.setWellAttribute(prodWell.name, self.attr_movingres        , prodWell.movingReservoir)
        self.setWellAttribute(prodWell.name, self.attr_multiprod        , prodWell.lastReservoirs )
        self.setWellAttribute(prodWell.name, self.attr_startDate        , self.mStartDate.date()  )
        self.setWellAttribute(prodWell.name, self.attrWellRole          , prodWell.wRole          )
        self.setWellAttribute(prodWell.name, self.attrWellStatus        , prodWell.wStatus        )
        self.setWellAttribute(prodWell.name, self.attrWellStatusReason  , prodWell.wStatusReason  )
        self.setWellAttribute(prodWell.name, self.attrWellStatusInfo    , prodWell.wStatusInfo    )
        if len(prodWell.liftMethod):
            self.setWellAttribute(prodWell.name, self.attrLiftMethod, prodWell.liftMethod)
        for i, fl in enumerate(bblInit.fluidCodes):
            self.setWellAttribute(prodWell.name, bblInit.attrFluidMass(  fl.code), sumMass[i])
            self.setWellAttribute(prodWell.name, bblInit.attrFluidVolume(fl.code), sumVols[i])

        for i, fl in enumerate(bblInit.fluidCodes):
            self.setWellAttribute(prodWell.name, bblInit.attrFluidMaxDebitMass(    fl.code), prodWell.maxDebits[i].massValue)
            self.setWellAttribute(prodWell.name, bblInit.attrFluidMaxDebitDateMass(fl.code), prodWell.maxDebits[i].massDebitDate)
            self.setWellAttribute(prodWell.name, bblInit.attrFluidMaxDebitVol(     fl.code), prodWell.maxDebits[i].volValue)
            self.setWellAttribute(prodWell.name, bblInit.attrFluidMaxDebitDateVol( fl.code), prodWell.maxDebits[i].volDebitDate)


    #==========================================================================
    # read production for selected well from  BASE
    #==========================================================================
    def readWellProduction(self, prodWell):
        #TableUnit = namedtuple('TableUnit', ['table', 'unit'])
        #prodTables = [
        #                TableUnit("p_std_vol_lq",   "Volume"), 
        #                TableUnit("p_std_vol_gas",  "Volume"), 
        #                TableUnit("p_q_mass_basis", "Mass")
        #                ]
        
        time_start=time.time()

        self.bblCalcReservoirMovingAndMultipleReservoirProduction(prodWell)
        IS_DEBUG and QgsMessageLog.logMessage(u"bblCalcReservoirMovingAndMultipleReservoirProduction  in {}".format((time.time() - time_start)/60), tag="QgisPDS.readWellProduction")
        time_start=time.time()
        i = 0
        
        # ---1 generate query for all bblInit item  like 'oil_Volume,oil_Mass...'
        prod_tables=set()
        query_fields=[
                        "start_time"
                        ,"end_time"
                        ,"start_time_txt"
                        ,"end_time_txt"
                        ,"days"
                        ,"reservoir_group"
                        ]
        FluidFields=namedtuple('FluidFields', ['code', 'idx','field','unit'])
        fluid_fields=[]
        sql_1=""
        for idx,fluidCode in enumerate(bblInit.fluidCodes):
            for tu in fluidCode.sourceTables:
                prod_tables.add(tu.table)
                if sql_1:
                    sql_1+=",\n"      
                sql_1+=u" sum(case when tmp_prod.SOURCE_T='{tbl_name}'   and tmp_prod.BSASC_SOURCE in ('{source_fluids}') then tmp_prod.DATA_VALUE else 0 end) {field_name}_{tbl_unit}".format(
                            tbl_name=tu.table
                            ,source_fluids= fluidCode.componentId if  fluidCode.componentId is not None else "','".join(fluidCode.subComponentIds)    
                            ,tbl_unit=tu.unit
                            ,field_name=fluidCode.code
                           )
                fluid_fields.append(
                            FluidFields(
                                        code=fluidCode.code
                                        ,idx=idx
                                        ,field="{field_name}_{tbl_unit}".format( field_name=fluidCode.code,tbl_unit=tu.unit )
                                        ,unit=tu.unit
                                        )
                                    )
        query_fields.extend(ff.field for ff in fluid_fields )
        # ---2 now generate UNION table with prod 
        sql_2 = ""
        for tbl_name in prod_tables:            
            if sql_2:
                sql_2 += u" union all "
            sql_2 +=u"""
                select 
                        '{tbl_name}' as SOURCE_T
                        ,{tbl_name}_s as SOURCE_S
                        ,DATA_VALUE
                        ,DATA_VALUE_U
                        ,ACTIVITY_S
                        ,ACTIVITY_T
                        ,BSASC_SOURCE
                    FROM    {tbl_name} 
                    WHERE DATA_VALUE is not Null
                        AND (DATA_VALUE>0 or DATA_VALUE<0)
                        AND ACTIVITY_T='PRODUCTION_ALOC'
                        {st_time_filter}
                        {en_time_filter}
                        
            """.format(
                tbl_name=tbl_name
                ,st_time_filter="AND START_TIME>="+self.to_oracle_date(self.mStartDate)
                ,en_time_filter="AND END_TIME<="+self.to_oracle_date(self.mEndDate)
                )
        # ---3 now generate full QUERY   
        sql=u"""
            SELECT
                pa.START_TIME             START_TIME
                ,pa.END_TIME              END_TIME
                ,{st_time}  
                ,{en_time}
                ,max(ppt.DATA_VALUE)/86400.0  WORK_DAYS 
                ,reservoirs.group_name        
                ,{prod_select}
            FROM
                (
                    SELECT grp.RESERVOIR_PART_CODE group_name
                            ,wbi.GEOLOGIC_FTR_S reservoir_part_s
                            ,twh.TIG_LATEST_WELL_NAME
                    FROM 
                        RESERVOIR_PART grp
                        ,EARTH_POS_RGN epr
                        ,TOPOLOGICAL_REL tr
                        ,wellbore_intv wbi
                        ,wellbore wb
                        ,well w
                        ,tig_well_history twh
                        
                    where 
                         epr.GEOLOGIC_FTR_S=grp.RESERVOIR_PART_S
                         AND
                         epr.GEOLOGIC_FTR_T='RESERVOIR_PART'
                         AND
                         tr.PRIM_TOPLG_OBJ_S =epr.EARTH_POS_RGN_S
                         AND
                         tr.PRIM_TOPLG_OBJ_T='EARTH_POS_RGN'
                         AND
                         tr.SEC_TOPLG_OBJ_T = 'WELLBORE_INTV'
                         AND
                         tr.SEC_TOPLG_OBJ_S = wbi.WELLBORE_INTV_S
                         AND
                         wbi.GEOLOGIC_FTR_T='RESERVOIR_PART'
                         AND 
                         wb.WELLBORE_S=wbi.WELLBORE_S
                         AND
                         w.WELL_S=wb.WELL_S
                         AND
                         twh.TIG_LATEST_WELL_NAME=w.WELL_ID
                         {twh_filter} 
                         {reservoir_filter}
                ) reservoirs
                left join PFNU_PROD_ACT_X ppax 
                    ON
                        ppax.PFNU_S=reservoirs.reservoir_part_s
                        AND
                        upper(ppax.PFNU_T)='RESERVOIR_PART'
                        AND
                        upper(ppax.PRODUCTION_ACT_T)='PRODUCTION_ALOC'
                left join PRODUCTION_ALOC pa
                    ON
                        pa.PRODUCTION_ALOC_S= ppax.PRODUCTION_ACT_S
                        AND
                        pa.bsasc_source = 'Reallocated Production'
                 join   ({prod_table}) tmp_prod 
                    ON
                        tmp_prod.ACTIVITY_S=pa.PRODUCTION_ALOC_S
                        AND           
                        tmp_prod.ACTIVITY_T='PRODUCTION_ALOC'
                left join p_pfnu_port_time ppt
                    ON 
                        ppt.activity_s = pa.production_aloc_s 
                        AND             
                        ppt.activity_t ='PRODUCTION_ALOC'
                        AND
                        ppt.data_value is not Null ---filter time,take only record with value. So not need filter by BSASC_SOURCE -production,water injection,gas injection
            where
                pa.bsasc_source = 'Reallocated Production'
                {phase_filter}
                {st_time_filter}
                {en_time_filter}
            group by 
                pa.START_TIME
                ,pa.END_TIME
                ,pa.PROD_START_TIME
                ,pa.PROD_END_TIME
                ,pa.BSASC_SOURCE
                ,reservoirs.group_name
            order by
                pa.START_TIME
                ,pa.END_TIME
                ,pa.PROD_START_TIME
                ,pa.PROD_END_TIME
                ,reservoirs.group_name            
        """.format(
            prod_select=sql_1
            ,prod_table=sql_2
            ,st_time=self.to_oracle_char("pa.start_time")
            ,en_time=self.to_oracle_char("pa.end_time")
            ,phase_filter=u" AND tmp_prod.bsasc_source in ('" + "','".join(self.mPhaseFilter) + "')"  if  self.mPhaseFilter else  ""
            ,twh_filter=u" AND twh.DB_SLDNID ="+ str(prodWell.sldnid) 
            ,st_time_filter=u"AND pa.START_TIME>="+self.to_oracle_date(self.mStartDate)
            ,en_time_filter=u"AND pa.END_TIME<="+self.to_oracle_date(self.mEndDate)
            ,reservoir_filter=u"AND grp.RESERVOIR_PART_CODE in ('" + u"','".join(self.mSelectedReservoirs) +u"')"
            )
        # ---4 execute QUERY
        IS_DEBUG and QgsMessageLog.logMessage(u"Execute readWellProduction: {}\n\n".format(sql), tag="QgisPDS.sql")
        result = self.db.execute(sql)
        IS_DEBUG and QgsMessageLog.logMessage(u"query in {}".format((time.time() - time_start)/60), tag="QgisPDS.readWellProduction")
        time_start=time.time()
        
        if result is None: 
            return
    
        # ---5 read QUERY result
        #fluids=[f.code for f in  bblInit.fluidCodes]
        product = None
        useLiftMethod = False
        # @TODO: not optimal code. Need change...
        for row in result:
            row_dict=dict(zip(query_fields,row))
            #QgsMessageLog.logMessage(u"result row: {}".format(row_dict), tag="QgisPDS.readWellProduction")
            #Max component debits for well
            stadat = QDateTime.fromString(row_dict["start_time_txt"], self.dateFormat)
            enddat = QDateTime.fromString(row_dict["end_time_txt"], self.dateFormat)
            days=row_dict["days"]
            if row_dict["days"]>0:
                for fluid in fluid_fields:
                    debit=row_dict[fluid.field]/days
                    if fluid.unit=="Mass":
                        if prodWell.maxDebits[fluid.idx].massValue < debit:
                            prodWell.maxDebits[fluid.idx].massValue = debit
                            prodWell.maxDebits[fluid.idx].massDebitDate = stadat
                    else:
                        if prodWell.maxDebits[fluid.idx].volValue < debit:
                            prodWell.maxDebits[fluid.idx].volValue = debit
                            prodWell.maxDebits[fluid.idx].volDebitDate = stadat
            if (stadat >= self.mStartDate and stadat <= self.mEndDate) or (enddat >= self.mStartDate and enddat <= self.mEndDate):
                useLiftMethod = True
                NeedProd = True
                if product is not None :
                    NeedProd = product.stadat!=stadat or product.enddat!=enddat
                if product is None or NeedProd:
                    #init clear production record
                    product = Production([0 for c in bblInit.fluidCodes], [0 for c in bblInit.fluidCodes], stadat, enddat, days)
                    prodWell.prods.append(product)
                for fluid in fluid_fields:
                    if fluid.unit=="Mass":
                        product.massVals[fluid.idx] += row_dict[fluid.field]
                    else:
                        product.volumeVals[fluid.idx] += row_dict[fluid.field]
        IS_DEBUG and QgsMessageLog.logMessage(u"row init in {}".format((time.time() - time_start)/60), tag="QgisPDS.readWellProduction")
        time_start=time.time()

        if useLiftMethod:
            liftMethod = self.getWellStrProperty(prodWell.sldnid, self.mEndDate, "lift method")
            if liftMethod in bblInit.bblLiftMethods.keys():
                prodWell.liftMethod = liftMethod
            IS_DEBUG and QgsMessageLog.logMessage(u"lift method in {}".format((time.time() - time_start)/60), tag="QgisPDS.readWellProduction")
    #==========================================================================
    # read production for selected wells from  BASE
    #==========================================================================
    def readWellsProduction(self, prodWells=[]):
        #TableUnit = namedtuple('TableUnit', ['table', 'unit'])
        #prodTables = [
        #                TableUnit("p_std_vol_lq",   "Volume"), 
        #                TableUnit("p_std_vol_gas",  "Volume"), 
        #                TableUnit("p_q_mass_basis", "Mass")
        #                ]
        if not isinstance(prodWells,list):
            prodWells=[prodWells]
        prodWells_dict=dict(zip(
                            map(lambda prodwell:str(prodwell.sldnid),prodWells)
                            ,prodWells
                            ))   
        well_ids_500=[map(lambda prodwell:str(prodwell.sldnid),prodWells[i:i + 500]) for i in xrange(0, len(prodWells), 500)]
            
            
        time_start=time.time()
        for prodWell in prodWells:
            self.bblCalcReservoirMovingAndMultipleReservoirProduction(prodWell)
        IS_DEBUG and QgsMessageLog.logMessage(u"bblCalcReservoirMovingAndMultipleReservoirProduction  in {}".format((time.time() - time_start)/60), tag="QgisPDS.readWellProduction")
        time_start=time.time()
        i = 0
        
        # ---1 generate query for all bblInit item  like 'oil_Volume,oil_Mass...'
        prod_tables=set()
        query_fields=[
                        "tig_well_id"
                        ,"start_time"
                        ,"end_time"
                        ,"start_time_txt"
                        ,"end_time_txt"
                        ,"days"
                        ,"reservoir_group"
                        ]
        FluidFields=namedtuple('FluidFields', ['code', 'idx','field','unit'])
        fluid_fields=[]
        sql_1=""
        for idx,fluidCode in enumerate(bblInit.fluidCodes):
            for tu in fluidCode.sourceTables:
                prod_tables.add(tu.table)
                if sql_1:
                    sql_1+=",\n"      
                sql_1+=u" sum(case when tmp_prod.SOURCE_T='{tbl_name}'   and tmp_prod.BSASC_SOURCE in ('{source_fluids}') then tmp_prod.DATA_VALUE else 0 end) {field_name}_{tbl_unit}".format(
                            tbl_name=tu.table
                            ,source_fluids= fluidCode.componentId if  fluidCode.componentId is not None else "','".join(fluidCode.subComponentIds)    
                            ,tbl_unit=tu.unit
                            ,field_name=fluidCode.code
                           )
                fluid_fields.append(
                            FluidFields(
                                        code=fluidCode.code
                                        ,idx=idx
                                        ,field="{field_name}_{tbl_unit}".format( field_name=fluidCode.code,tbl_unit=tu.unit )
                                        ,unit=tu.unit
                                        )
                                    )
        query_fields.extend(ff.field for ff in fluid_fields )
        # ---2 now generate UNION table with prod 
        sql_2 = ""
        for tbl_name in prod_tables:            
            if sql_2:
                sql_2 += u" union all "
            sql_2 +=u"""
                select 
                        '{tbl_name}' as SOURCE_T
                        ,{tbl_name}_s as SOURCE_S
                        ,DATA_VALUE
                        ,DATA_VALUE_U
                        ,ACTIVITY_S
                        ,ACTIVITY_T
                        ,BSASC_SOURCE
                    FROM    {tbl_name} 
                    WHERE DATA_VALUE is not Null
                        AND (DATA_VALUE>0 or DATA_VALUE<0)
                        AND ACTIVITY_T='PRODUCTION_ALOC'
                        {st_time_filter}
                        {en_time_filter}
                        
            """.format(
                tbl_name=tbl_name
                ,st_time_filter="AND START_TIME>="+self.to_oracle_date(self.mStartDate)
                ,en_time_filter="AND END_TIME<="+self.to_oracle_date(self.mEndDate)
                )
        # ---3 now generate full QUERY
        sql=u""
        for well_ids in well_ids_500:
            IS_DEBUG and QgsMessageLog.logMessage(u"Make sql for wells: {}\n\n".format(well_ids), tag="QgisPDS.debug")
            if bool(sql):sql+="\nUNION ALL\n"
            sql+=u"""
                SELECT
                    TO_CHAR(reservoirs.TIG_WELL_ID)     TIG_WELL_ID
                    ,pa.START_TIME                      START_TIME
                    ,pa.END_TIME                        END_TIME
                    ,{st_time}  
                    ,{en_time}
                    ,max(ppt.DATA_VALUE)/86400.0  WORK_DAYS 
                    ,reservoirs.group_name        
                    ,{prod_select}
                FROM
                    (
                        SELECT grp.RESERVOIR_PART_CODE group_name
                                ,wbi.GEOLOGIC_FTR_S reservoir_part_s
                                ,twh.TIG_LATEST_WELL_NAME
                                ,twh.DB_SLDNID  TIG_WELL_ID
                        FROM 
                            RESERVOIR_PART grp
                            ,EARTH_POS_RGN epr
                            ,TOPOLOGICAL_REL tr
                            ,wellbore_intv wbi
                            ,wellbore wb
                            ,well w
                            ,tig_well_history twh
                            
                        where 
                             epr.GEOLOGIC_FTR_S=grp.RESERVOIR_PART_S
                             AND
                             epr.GEOLOGIC_FTR_T='RESERVOIR_PART'
                             AND
                             tr.PRIM_TOPLG_OBJ_S =epr.EARTH_POS_RGN_S
                             AND
                             tr.PRIM_TOPLG_OBJ_T='EARTH_POS_RGN'
                             AND
                             tr.SEC_TOPLG_OBJ_T = 'WELLBORE_INTV'
                             AND
                             tr.SEC_TOPLG_OBJ_S = wbi.WELLBORE_INTV_S
                             AND
                             wbi.GEOLOGIC_FTR_T='RESERVOIR_PART'
                             AND 
                             wb.WELLBORE_S=wbi.WELLBORE_S
                             AND
                             w.WELL_S=wb.WELL_S
                             AND
                             twh.TIG_LATEST_WELL_NAME=w.WELL_ID
                             {twh_filter} 
                             {reservoir_filter}
                    ) reservoirs
                    left join PFNU_PROD_ACT_X ppax 
                        ON
                            ppax.PFNU_S=reservoirs.reservoir_part_s
                            AND
                            upper(ppax.PFNU_T)='RESERVOIR_PART'
                            AND
                            upper(ppax.PRODUCTION_ACT_T)='PRODUCTION_ALOC'
                    left join PRODUCTION_ALOC pa
                        ON
                            pa.PRODUCTION_ALOC_S= ppax.PRODUCTION_ACT_S
                            AND
                            pa.bsasc_source = 'Reallocated Production'
                     join   ({prod_table}) tmp_prod 
                        ON
                            tmp_prod.ACTIVITY_S=pa.PRODUCTION_ALOC_S
                            AND           
                            tmp_prod.ACTIVITY_T='PRODUCTION_ALOC'
                    left join p_pfnu_port_time ppt
                        ON 
                            ppt.activity_s = pa.production_aloc_s 
                            AND             
                            ppt.activity_t ='PRODUCTION_ALOC'
                            AND
                            ppt.data_value is not Null ---filter time,take only record with value. So not need filter by BSASC_SOURCE -production,water injection,gas injection
                where
                    pa.bsasc_source = 'Reallocated Production'
                    {phase_filter}
                    {st_time_filter}
                    {en_time_filter}
                group by 
                    pa.START_TIME
                    ,pa.END_TIME
                    ,pa.PROD_START_TIME
                    ,pa.PROD_END_TIME
                    ,pa.BSASC_SOURCE
                    ,reservoirs.group_name
                    ,reservoirs.TIG_WELL_ID
            """.format(
                prod_select=sql_1
                ,prod_table=sql_2
                ,st_time=self.to_oracle_char("pa.start_time")
                ,en_time=self.to_oracle_char("pa.end_time")
                ,phase_filter=u" AND tmp_prod.bsasc_source in ('" + "','".join(self.mPhaseFilter) + "')"  if  self.mPhaseFilter else  ""
                ,twh_filter=u" AND twh.DB_SLDNID in ('{}')".format("','".join(well_ids)) 
                ,st_time_filter=u"AND pa.START_TIME>="+self.to_oracle_date(self.mStartDate)
                ,en_time_filter=u"AND pa.END_TIME<="+self.to_oracle_date(self.mEndDate)
                ,reservoir_filter=u"AND grp.RESERVOIR_PART_CODE in ('" + u"','".join(self.mSelectedReservoirs) +u"')"
                )
        if bool(sql):
            sql+="""
                order by
                    TIG_WELL_ID
                    ,START_TIME
                    ,END_TIME
                    ,group_name            
                """
        else:
            return
        # ---4 execute QUERY
        IS_DEBUG and QgsMessageLog.logMessage(u"Execute readWellProduction: {}\n\n".format(sql), tag="QgisPDS.sql")
        result = self.db.execute(sql)
        IS_DEBUG and QgsMessageLog.logMessage(u"query in {}".format((time.time() - time_start)/60), tag="QgisPDS.readWellProduction")
        time_start=time.time()
        
        if result is None: 
            return
    
        # ---5 read QUERY result
        # @TODO: not optimal code. Need change...
        for row in result:
            row_dict=dict(zip(query_fields,row))
            #QgsMessageLog.logMessage(u"result row: {}".format(row_dict), tag="QgisPDS.readWellProduction")
            #Max component debits for well
            tig_well_id=row_dict["tig_well_id"]
            prodWell=prodWells_dict[tig_well_id]
            stadat = QDateTime.fromString(row_dict["start_time_txt"], self.dateFormat)
            enddat = QDateTime.fromString(row_dict["end_time_txt"]  , self.dateFormat)
            days=row_dict["days"]
            if row_dict["days"]>0:
                for fluid in fluid_fields:
                    debit=row_dict[fluid.field]/days
                    if fluid.unit=="Mass":
                        if prodWell.maxDebits[fluid.idx].massValue < debit:
                            prodWell.maxDebits[fluid.idx].massValue = debit
                            prodWell.maxDebits[fluid.idx].massDebitDate = stadat
                    else:
                        if prodWell.maxDebits[fluid.idx].volValue < debit:
                            prodWell.maxDebits[fluid.idx].volValue = debit
                            prodWell.maxDebits[fluid.idx].volDebitDate = stadat
            if (stadat >= self.mStartDate and stadat <= self.mEndDate) or (enddat >= self.mStartDate and enddat <= self.mEndDate):
                #init clear production record
                product = Production([0 for c in bblInit.fluidCodes], [0 for c in bblInit.fluidCodes], stadat, enddat, days)
                prodWell.prods.append(product)
                for fluid in fluid_fields:
                    if fluid.unit=="Mass":
                        product.massVals[fluid.idx] += row_dict[fluid.field]
                    else:
                        product.volumeVals[fluid.idx] += row_dict[fluid.field]
        for id,prodWell in prodWells_dict.items():
            liftMethod = self.getWellStrProperty(prodWell.sldnid, self.mEndDate, "lift method")
            if liftMethod in bblInit.bblLiftMethods.keys():
                prodWell.liftMethod = liftMethod
                
         
         
         
#===============================================================================
#         for prod, s1, e1, start_time, end_time, componentId, unitSet, wtime in result:
#             stadat = QDateTime.fromString(start_time, self.dateFormat)
#             enddat = QDateTime.fromString(end_time, self.dateFormat)
#             days = wtime/86400.0
# 
#         
#             #Max component debits for well
#             if componentId in fluids and days != 0.0:        #!!!!!!!!!!!!!!!!
#                 PhaseIndex = fluids.index(componentId)       #!!!!!!!!!!!!!!!!
#                 debit = prod / days
#                 if "Mass" in unitSet:
#                     if prodWell.maxDebits[PhaseIndex].massValue < debit:
#                         prodWell.maxDebits[PhaseIndex].massValue = debit
#                         prodWell.maxDebits[PhaseIndex].massDebitDate = stadat
#                 else:
#                     if prodWell.maxDebits[PhaseIndex].volValue < debit:
#                         prodWell.maxDebits[PhaseIndex].volValue = debit
#                         prodWell.maxDebits[PhaseIndex].volDebitDate = stadat
# 
#             if (stadat >= self.mStartDate and stadat <= self.mEndDate) or (enddat >= self.mStartDate and enddat <= self.mEndDate):
#                 useLiftMethod = True
#                 NeedProd = True
# 
#                 if product is not None :
#                     NeedProd = product.stadat!=stadat or product.enddat!=enddat
# 
#                 if product is None or NeedProd:
#                     product = Production([0 for c in bblInit.fluidCodes], [0 for c in bblInit.fluidCodes], stadat, enddat, days)
#                     prodWell.prods.append(product)
# 
#                 if componentId in fluids:                             #!!!!!!!!!!!!!!!!
#                     PhaseIndex = fluids.index(componentId)            #!!!!!!!!!!!!!!!!
#                     if "Mass" in unitSet:
#                         product.massVals[PhaseIndex] += prod
#                     else:
#                         product.volumeVals[PhaseIndex] += prod
#                 else:
#                     QgsMessageLog.logMessage( self.tr(u"No fluid for ") + componentId)        #!!!!!!!!!!!!!!!!
#         QgsMessageLog.logMessage(u"data parse in {}".format((time.time() - time_start)/60), tag="QgisPDS.readWellProduction")
#         time_start=time.time()
# 
#         if useLiftMethod:
#             liftMethod = self.getWellStrProperty(prodWell.sldnid, self.mEndDate, "lift method")
#             if liftMethod in bblInit.bblLiftMethods.keys():
#                 prodWell.liftMethod = liftMethod
#             QgsMessageLog.logMessage(u"lift method in {}".format((time.time() - time_start)/60), tag="QgisPDS.readWellProduction")
#===============================================================================
        
    #===========================================================================
    # Load production wells
    #===========================================================================
    def getWells(self, cmpl_id):
        if self.isCurrentProd:
            sql = ("SELECT DISTINCT well.WELL_ID"
                "    FROM  reservoir_part,"
                "    wellbore_intv,"
                "    wellbore,"
                "    well,"
                "    production_aloc,"
                "    pfnu_prod_act_x,"
                "    (SELECT"
                "        wellbore.WELL_ID w_id,"
                "        MAX(PRODUCTION_ALOC.START_TIME) max_time"
                "      FROM  reservoir_part,"
                "        wellbore_intv,"
                "        wellbore,"
                "        production_aloc,"
                "        pfnu_prod_act_x"
                "      WHERE PRODUCTION_ALOC.PRODUCTION_ALOC_S = PFNU_PROD_ACT_X.PRODUCTION_ACT_S"
                "        and production_aloc.bsasc_source = 'Reallocated Production'"
                "        and reservoir_part.reservoir_part_s = pfnu_prod_act_x.pfnu_s"
                "        and wellbore_intv.geologic_ftr_s = reservoir_part.reservoir_part_s"
                "        and wellbore.wellbore_s=wellbore_intv.wellbore_s"
                "        AND PRODUCTION_ALOC.START_TIME <= " + self.to_oracle_date(self.mEndDate) +
                "      GROUP BY wellbore.WELL_ID) md, "
                "    (select wellbore_intv.geologic_ftr_s ftr_s"
                "           from earth_pos_rgn, wellbore_intv, topological_rel, reservoir_part "
                "           where earth_pos_rgn_s = topological_rel.prim_toplg_obj_s "
                "           and wellbore_intv_s = topological_rel.sec_toplg_obj_s "
                "           and earth_pos_rgn.geologic_ftr_s = reservoir_part_s "
                "           and entity_type_nm = 'RESERVOIR_ZONE' "
                "           and reservoir_part_code in ('" + "','".join(self.mSelectedReservoirs) +"')) res"
                "    WHERE PRODUCTION_ALOC.PRODUCTION_ALOC_S = PFNU_PROD_ACT_X.PRODUCTION_ACT_S"
                "      and production_aloc.bsasc_source = 'Reallocated Production'"
                "      and reservoir_part.reservoir_part_s = pfnu_prod_act_x.pfnu_s"
                "      AND PRODUCTION_ALOC.START_TIME = md.max_time"
                "      AND PRODUCTION_ALOC.START_TIME <= " + self.to_oracle_date(self.mEndDate) +
                "      AND wellbore.WELL_ID=md.w_id"
                "      and reservoir_part.reservoir_part_s = res.ftr_s"
                "      and wellbore_intv.geologic_ftr_s = reservoir_part.reservoir_part_s"
                "      and wellbore.wellbore_s=wellbore_intv.wellbore_s"
                "      and well.well_s=wellbore.well_s")
        else:
            sql = ("SELECT DISTINCT well.WELL_ID"
                "    FROM  reservoir_part,"
                "    wellbore_intv,"
                "    wellbore,"
                "    well,"
                "    production_aloc,"
                "    pfnu_prod_act_x, "
                "    (select wellbore_intv.geologic_ftr_s ftr_s"
                "           from earth_pos_rgn, wellbore_intv, topological_rel, reservoir_part "
                "           where earth_pos_rgn_s = topological_rel.prim_toplg_obj_s "
                "           and wellbore_intv_s = topological_rel.sec_toplg_obj_s "
                "           and earth_pos_rgn.geologic_ftr_s = reservoir_part_s "
                "           and entity_type_nm = 'RESERVOIR_ZONE' "
                "           and reservoir_part_code in ('" + "','".join(self.mSelectedReservoirs) +"')) res"
                "    WHERE PRODUCTION_ALOC.PRODUCTION_ALOC_S = PFNU_PROD_ACT_X.PRODUCTION_ACT_S"
                "      and production_aloc.bsasc_source = 'Reallocated Production'"
                "      and reservoir_part.reservoir_part_s = pfnu_prod_act_x.pfnu_s"
                "      AND PRODUCTION_ALOC.START_TIME >= " + self.to_oracle_date(self.mStartDate) +
                "      AND PRODUCTION_ALOC.START_TIME <= " + self.to_oracle_date(self.mEndDate) +
                "      and reservoir_part.reservoir_part_s = res.ftr_s"
                "      and wellbore_intv.geologic_ftr_s = reservoir_part.reservoir_part_s"
                "      and wellbore.wellbore_s=wellbore_intv.wellbore_s"
                "      and well.well_s=wellbore.well_s")
        IS_DEBUG and QgsMessageLog.logMessage(u"Execute getWells: {}\\n\n".format(sql), tag="QgisPDS.sql")
        result = self.db.execute(sql)

        for wl in result:
            self.loadWellByName(to_unicode("".join(wl)))

    # def getWells(self, cmpl_id):
    #     if self.isCurrentProd:
    #         sql = ("SELECT DISTINCT wellbore.WELL_ID"
    #                "    FROM  reservoir_part,"
    #                "    wellbore_intv,"
    #                "    wellbore,"
    #                "    production_aloc,"
    #                "    pfnu_prod_act_x,"
    #                "      (SELECT"
    #                "        wellbore.WELL_ID w_id,"
    #                "        MAX(PRODUCTION_ALOC.START_TIME) max_time"
    #                "      FROM  reservoir_part,"
    #                "        wellbore_intv,"
    #                "        wellbore,"
    #                "        production_aloc,"
    #                "        pfnu_prod_act_x"
    #                "      WHERE PRODUCTION_ALOC.PRODUCTION_ALOC_S = PFNU_PROD_ACT_X.PRODUCTION_ACT_S"
    #                "        and production_aloc.bsasc_source = 'Reallocated Production'"
    #                "        and reservoir_part.reservoir_part_s = pfnu_prod_act_x.pfnu_s"
    #                "        and wellbore_intv.geologic_ftr_s = reservoir_part.reservoir_part_s"
    #                "        and wellbore.wellbore_s=wellbore_intv.wellbore_s"
    #                "        AND PRODUCTION_ALOC.START_TIME <= " + self.to_oracle_date(self.mEndDate) +
    #                "      GROUP BY wellbore.WELL_ID) md"
    #                "    WHERE PRODUCTION_ALOC.PRODUCTION_ALOC_S = PFNU_PROD_ACT_X.PRODUCTION_ACT_S"
    #                "      and production_aloc.bsasc_source = 'Reallocated Production'"
    #                "      and reservoir_part.reservoir_part_s = pfnu_prod_act_x.pfnu_s"
    #                "      AND PRODUCTION_ALOC.START_TIME = md.max_time"
    #                "      AND PRODUCTION_ALOC.START_TIME <= " + self.to_oracle_date(self.mEndDate) +
    #                "      AND wellbore.WELL_ID=md.w_id"
    #                "      and reservoir_part.reservoir_part_s in (" + cmpl_id + ")"
    #                "      and wellbore_intv.geologic_ftr_s = reservoir_part.reservoir_part_s"
    #                "      and wellbore.wellbore_s=wellbore_intv.wellbore_s")
    #     else:
    #         sql = ("SELECT DISTINCT wellbore.WELL_ID"
    #                "    FROM  reservoir_part,"
    #                "    wellbore_intv,"
    #                "    wellbore,"
    #                "    production_aloc,"
    #                "    pfnu_prod_act_x"
    #                "    WHERE PRODUCTION_ALOC.PRODUCTION_ALOC_S = PFNU_PROD_ACT_X.PRODUCTION_ACT_S"
    #                "      and production_aloc.bsasc_source = 'Reallocated Production'"
    #                "      and reservoir_part.reservoir_part_s = pfnu_prod_act_x.pfnu_s"
    #                "      AND PRODUCTION_ALOC.START_TIME >= " + self.to_oracle_date(self.mStartDate) +
    #                "      AND PRODUCTION_ALOC.START_TIME <= " + self.to_oracle_date(self.mEndDate) +
    #                "      and reservoir_part.reservoir_part_s in (" + cmpl_id + ")"
    #                "      and wellbore_intv.geologic_ftr_s = reservoir_part.reservoir_part_s"
    #                "      and wellbore.wellbore_s=wellbore_intv.wellbore_s")
    #
    #     result = self.db.execute(sql)
    #
    #     for wl in result:
    #         self.loadWellByName(to_unicode("".join(wl)))
    
    
    #===========================================================================
    # Load well by name
    #===========================================================================
    def loadWellByName(self, well_name):
        sql = ("SELECT db_sldnid FROM tig_well_history "
                "WHERE rtrim(tig_latest_well_name) = '" + well_name + "' "
                "AND (tig_only_proposal = 0 OR tig_only_proposal = 1) ")

        IS_DEBUG and QgsMessageLog.logMessage(u"Execute loadWellByName: {}\\n\n".format(sql), tag="QgisPDS.sql")
        result = self.db.execute(sql)
        for id in result:
            wId = id[0]
            #if wId!=682:continue # @DEBUG
            symbolId,role,status,status_reason,status_info = self.bbl_wellsymbol(wId)
            self.loadWellFeature(wId, symbolId)
            pwp = ProductionWell(name=well_name, sldnid=wId, liftMethod='', prods=[],
                                 maxDebits = [ProdDebit() for c in bblInit.fluidCodes]
                                 ,wRole = role
                                 ,wStatus = status
                                 ,wStatusReason = status_reason 
                                 ,wStatusInfo = status_info


                                 )
            self.mProductionWells.append(pwp)

    #===========================================================================
    # 
    #===========================================================================
    def bblCalcReservoirMovingAndMultipleReservoirProduction(self, prodWell):
        sql = ("SELECT "    
             " reservoir_part.reservoir_part_code, "
             + self.to_oracle_char("PRODUCTION_ALOC.prod_end_time") +
             " FROM "
             " reservoir_part, "
             " wellbore_intv, "
             " wellbore, "
             " well, "
             " tig_well_history, "
             " PFNU_PROD_ACT_X, "
             " PRODUCTION_ALOC "
             " WHERE "
             " production_aloc.PRODUCTION_ALOC_S = pfnu_prod_act_x.PRODUCTION_ACT_S "
             " and production_aloc.bsasc_source = 'Reallocated Production'"
             " and reservoir_part.reservoir_part_s = pfnu_prod_act_x.pfnu_s"
             " and wellbore_intv.geologic_ftr_s = reservoir_part.reservoir_part_s"
             " and wellbore.wellbore_s=wellbore_intv.wellbore_s"
             " and well.well_s=wellbore.well_s"
             " and tig_well_history.tig_latest_well_name=well.well_id"
             " and tig_well_history.DB_SLDNID = "+ str(prodWell.sldnid) +
             " AND PRODUCTION_ALOC.prod_start_time <=  " + self.to_oracle_date(self.mEndDate) +
             " order by prod_end_time, reservoir_part_code")

        prevProdEndTime = ''
        prevResvs = None
        resvs = []
        multipleReservoirProductionResvs = []
        prevFindat = 1
        findat = 0

        IS_DEBUG and QgsMessageLog.logMessage(u"Execute bblCalcReservoirMovingAndMultipleReservoirProduction: {}\\n\n".format(sql), tag="QgisPDS.sql")
        result = self.db.execute(sql)
        for reservoirId,prodEndTime in result:
            if prevProdEndTime != prodEndTime:
                if prevResvs is not None:
                    intrescv = self.intersectReservoirs(resvs, self.reservoirs)
                    str1 = '+'.join([item.name for item in prevResvs])
                    str2 = '+'.join([item.name for item in resvs])

                    if len(intrescv) != 0 and not self.isEqualReservoirs(prevResvs,resvs):
                        subsResvs = self.subtractReservoirs(resvs, prevResvs)

                        if self.isEqualReservoirs(prevResvs, self.reservoirs):
                            prodWell.reservoirState = 'NO_MOVING'
                        elif self.isUpper(prevResvs, subsResvs):
                            prodWell.reservoirState = 'FROM_UPPER_RESERVOIR'
                            prodWell.movingReservoir = str1
                        elif self.isLower(prevResvs, subsResvs):
                            prodWell.reservoirState = 'FROM_LOWER_RESERVOIR'
                            prodWell.movingReservoir = str1

                    if len(intrescv) == 0 and len(self.intersectReservoirs(prevResvs, self.reservoirs)) != 0:
                        subsResvs = self.subtractReservoirs(prevResvs, resvs)

                        if self.isUpper(resvs, subsResvs):
                            prodWell.reservoirState = 'TO_UPPER_RESERVOIR'
                            prodWell.movingReservoir = str2
                        elif self.isLower(resvs, subsResvs):
                            prodWell.reservoirState = 'TO_LOWER_RESERVOIR'
                            prodWell.movingReservoir = str2

                prevResvs = resvs
                resvs = []
            resv = NAMES(name=reservoirId, selected=True)
            resvs.append(resv)
            prevProdEndTime = prodEndTime

            findat = QDateTime.fromString(prodEndTime, self.dateFormat)

            if findat != prevFindat:
                multipleReservoirProductionResvs = []
            if not reservoirId in [item.name for item in multipleReservoirProductionResvs]:
                multipleReservoirProductionResvs.append(NAMES(name=reservoirId, selected=True))

            prevFindat = findat

        prodWell.lastReservoirs = '+'.join([item.name for item in multipleReservoirProductionResvs])

    #===============================================================================
    # 
    #===============================================================================
    def _readAllWells(self):
        try:
            result = self.db.execute(
                "select tig_latest_well_name, db_sldnid, tig_latitude, tig_longitude from tig_well_history")

            for well_name, wId, lat, lon in result:
                if well_name not in self.mWells:
                    wellRole =        self.getWellStrProperty(wId, self.mEndDate, "current well role")
                    wellStatus =      self.getWellStrProperty(wId, self.mEndDate, "well status"      )
                    wellStatusDesc =  self.getWellStrProperty(wId, self.mEndDate, "well status",sqlColumn="description" )
                    wellStatusInfo=wellStatusReason=""
                    try:   wellStatusReason,wellStatusInfo = wellStatusDesc.split("|")
                    except:pass

                    well = QgsFeature (self.layer.fields()                                    )
                    well.setAttribute (self.attrWellId               , well_name              )
                    well.setAttribute (self.attrLatitude             , lat                    )
                    well.setAttribute (self.attrLongitude            , lon                    )
                    well.setAttribute (self.attrSymbol               , 71                     )
                    well.setAttribute (self.attrSymbolName           , self.tr('unknown well'))
                    well.setAttribute (self.attrWellRole             , wellRole               )
                    well.setAttribute (self.attrWellStatus           , wellStatus             )
                    well.setAttribute (self.attrWellStatusInfo       , wellStatusInfo         )
                    well.setAttribute (self.attrWellStatusReason     , wellStatusReason       )

                    if lon and lat and lon != NULL and lat != NULL:
                        pt = QgsPoint(lon, lat)
                        if self.xform:
                            pt = self.xform.transform(pt)
                        well.setGeometry(QgsGeometry.fromPoint(pt))
                        self.mWells[well_name] = well
                        pwp = ProductionWell(name=well_name, sldnid=wId, liftMethod='', prods=[],
                                             maxDebits=[ProdDebit() for c in bblInit.fluidCodes]
                                             ,wRole=wellRole
                                             ,wStatus=wellStatus
                                             ,wStatusReason=wellStatusReason
                                             ,wStatusInfo=wellStatusInfo

                                             )
                        self.mProductionWells.append(pwp)

        except Exception as e:
            QgsMessageLog.logMessage(u"Read wells from project : {}".format(str(e)), tag="QgisPDS.Error")
            return
    #===============================================================================
    # 
    #===============================================================================
    def bbl_wellsymbol(self, sldnid):
        initialWellRole = self.getWellStrProperty(sldnid, self.mEndDate, "initial well role")
        wellRole =        self.getWellStrProperty(sldnid, self.mEndDate, "current well role")
        wellStatus =      self.getWellStrProperty(sldnid, self.mEndDate, "well status"      )
        wellStatusDesc =  self.getWellStrProperty(sldnid, self.mEndDate, "well status",sqlColumn="description" )
        wellStatusInfo=wellStatusReason=""
        try:   wellStatusReason, wellStatusInfo = wellStatusDesc.split("|")
        except:pass

        
        #---not need cheeck initial well role at now
        #for conv in bblInit.bblConvertedSymbols:
        #    if (
        #        conv.initialWellRole == initialWellRole and
        #        conv.currentWellRole == wellRole and
        #        conv.wellStatus == wellStatus
        #        ):
        #        return SYMBOL(wellRole + ' ' + wellStatus, conv.symbol),wellRole,wellStatus
        for sym in bblInit.bblSymbols:
            if sym.wellRole == wellRole and sym.wellStatus == wellStatus:
                return SYMBOL(wellRole + ' '+ wellStatus, sym.symbol),wellRole,wellStatus,wellStatusReason,wellStatusInfo
#        sql = (" SELECT P_ALLOC_FACTOR.DATA_VALUE, WELL.WELL_ID, PRODUCTION_ALOC.START_TIME"
#                    " FROM ALOC_FLW_STRM ALOC_FLW_STRM, "
#                    " FLW_STRM_ALOC_FCT FLW_STRM_ALOC_FCT, "
#                    " P_ALLOC_FACTOR P_ALLOC_FACTOR,"
#                    " PFNU_PROD_ACT_X PFNU_PROD_ACT_X,"
#                    " PRODUCTION_ALOC PRODUCTION_ALOC, "
#                    " WELL WELL,"
#                    " WELL_COMPLETION WELL_COMPLETION"
#                    "   WHERE PRODUCTION_ALOC.PRODUCTION_ALOC_S = PFNU_PROD_ACT_X.PRODUCTION_ACT_S"
#                    "   AND WELL.WELL_S = WELL_COMPLETION.WELL_S AND"
#                    "   WELL_COMPLETION.WELL_COMPLETION_S = PFNU_PROD_ACT_X.PFNU_S AND"
#                    "   P_ALLOC_FACTOR.ACTIVITY_S = PRODUCTION_ALOC.PRODUCTION_ALOC_S AND"
#                    "   P_ALLOC_FACTOR.OBJECT_S = FLW_STRM_ALOC_FCT.FLW_STRM_ALOC_FCT_S AND"
#                    "   FLW_STRM_ALOC_FCT.INLET_ALOC_FLW_STRM_S = ALOC_FLW_STRM.ALOC_FLW_STRM_S AND"
#                    "   ((WELL.WELL_ID='"+well_name+"') AND (ALOC_FLW_STRM.FL_PSEUDO_CMPN_ID='pipeline') AND"
#                    "    (WELL_COMPLETION.WELL_COMPLETION_ID in ('"+cmpl_id+"')) AND"
#                    "    (PRODUCTION_ALOC.START_TIME <= "+ self.to_oracle_date(findat) +"))"
#                    " ORDER BY PRODUCTION_ALOC.START_TIME")

#        result = self.db.execute(sql)
#        for id in result:
#            data_val = id[0]
        return SYMBOL('unknown well', 70),wellRole,wellStatus,wellStatusReason, wellStatusInfo

    
    #===========================================================================
    # Load well geometry
    #===========================================================================
    def loadWellFeature(self, sldnid, symbolId):
        sql = ("select tig_latest_well_name, tig_latitude, tig_longitude "
                "  from tig_well_history where db_sldnid = " + str(sldnid))
        result = self.db.execute(sql)

        well = QgsFeature(self.layer.fields())
        plugin_dir = os.path.dirname(__file__)
        for well_name, lat, lon in result:
            well.setAttribute (self.attrWellId,    well_name)
            well.setAttribute (self.attrLatitude,  lat      )
            well.setAttribute (self.attrLongitude, lon      )
            if symbolId >= 0:
                well.setAttribute (self.attrSymbolId  , plugin_dir+"/svg/WellSymbol"+str(symbolId.symbol+1).zfill(3)+".svg")
                well.setAttribute (self.attrSymbol    , symbolId.symbol+1                                                  )
                well.setAttribute (self.attrSymbolName, symbolId.wellRole                                                  )
            pt = QgsPoint(lon, lat)
            if self.xform:
                pt = self.xform.transform(pt)
            well.setGeometry(QgsGeometry.fromPoint(pt))
            # well.setGeometry(QgsGeometry.fromPoint(QgsPoint(lon, lat)))
            self.mWells[well_name] = well
            

    #===========================================================================
    # Read equipment value of well
    #===========================================================================
    def getWellStrProperty(self, sldnid, enddat, propertyType, sqlColumn="string_value"):
        sql =   """
                 SELECT * from (
                     select 
                          p_equipment_fcl.{sqlColumn} 
                     from 
                         p_equipment_fcl
                         , equipment_insl 
                         , well
                         , tig_well_history 
                     where 
                         equipment_insl.equipment_item_s = p_equipment_fcl.object_s 
                         and 
                         well.well_s = equipment_insl.facility_s 
                         and 
                         tig_well_history.tig_latest_well_name = well.well_id 
                         and 
                         tig_well_history.db_sldnid = {sldnid} 
                         and 
                         p_equipment_fcl.bsasc_source = '{propertyType}' 
                         and 
                         p_equipment_fcl.start_time <= {enddat}
                     order by p_equipment_fcl.start_time desc
                ) WHERE ROWNUM=1
                """.format(
                            sldnid=str(sldnid)
                           ,propertyType=propertyType
                           ,enddat=self.to_oracle_date(enddat)
                           ,sqlColumn=sqlColumn
                           )
        IS_DEBUG and QgsMessageLog.logMessage(u"Execute getWellStrProperty: {}\\n\n".format(sql), tag="QgisPDS.sql")   
        result = self.db.execute(sql)

        propertyValue = ""
        for row in result:
            propertyValue = row[0]
        return propertyValue

    #===========================================================================
    # Return TO_DATE oracle string 
    #===========================================================================
    def to_oracle_date(self, qDate):
        # dateText = qDate.toString(self.dateFormat)
        # return "TO_DATE('"+dateText+"', 'DD/MM/YYYY HH24:MI:SS')"
        return self.db.stringToSqlDate(qDate)
    #=======================================================================
    # 
    #=======================================================================
    def to_oracle_char(self, field):
        return self.db.formatDateField(field)
        # return "TO_CHAR(" + field + ", 'DD/MM/YYYY HH24:MI:SS')"
        
    #===========================================================================
    # return selected in reservoirsListWidget items
    #===========================================================================
    def getSelectedReservoirs(self):
        selectedReservoirs = []
            
        for item in self.reservoirsListWidget.selectedItems():
            selectedReservoirs.append(item.text())
          
        return selectedReservoirs
        
        
    #===========================================================================
    # Return comma separeted string of SLDNID`s of selected reservoirs
    #===========================================================================
    def getReservoirsFilter(self):
        sql = ("select wellbore_intv.geologic_ftr_s "
                "from earth_pos_rgn, wellbore_intv, topological_rel, reservoir_part "
                "where earth_pos_rgn_s = topological_rel.prim_toplg_obj_s "
                "and wellbore_intv_s = topological_rel.sec_toplg_obj_s "
                "and earth_pos_rgn.geologic_ftr_s = reservoir_part_s "
                "and entity_type_nm = 'RESERVOIR_ZONE' "
                "and reservoir_part_code in ('" + "','".join(self.mSelectedReservoirs) +"')")
                
        result = self.db.execute(sql)     

        return ",".join([to_unicode("".join(p)) for p in result])

    #===========================================================================
    # 
    #===========================================================================
    def bbl_getproduction_period(self, OnlyProduction):
        connection = create_connection(self.project)
        scheme = self.project['project']

        try:
            db = connection.get_db(scheme)
            
            sql = ""
            if OnlyProduction:
                sql =  (" select {0},"
                        " {1} from p_std_vol_lq production, production_aloc"
                        " WHERE production.activity_s = production_aloc.production_aloc_s and"
                        " production_aloc.bsasc_source = 'Reallocated Production'")\
                        .format(db.formatDateField('min(production.start_time)'), db.formatDateField('max(production.end_time)'))
            else:
                sql = (" select {0} start_date,"
                        " {1} end_date"
                        " from"
                        " (select min(production.start_time) start_date,"
                        " max(production.end_time) end_date from p_std_vol_lq production, production_aloc"
                        " WHERE production.activity_s = production_aloc.production_aloc_s and"
                        " production_aloc.bsasc_source = 'Reallocated Production'"
                        " union"
                        " select  min(wtst_meas.start_time) start_date,"
                        " max(wtst_meas.end_time) end_date"
                        " from wtst_meas)")\
                    .format(db.formatDateField('min(start_date)'), db.formatDateField('max(end_date)'))

            result = db.execute(sql)

            if result is not None:
                for minD, maxD in result:
                    self.realStartDate = QDateTime.fromString(minD, self.dateFormat)
                    self.realEndDate = QDateTime.fromString(maxD, self.dateFormat)

            db.disconnect()
        except Exception as e:
            QgsMessageLog.logMessage(u"Read production from project : {}".format(str(e)), tag="QgisPDS.Error")

     
    #===========================================================================
    # return selected in fluidsListWidget items   
    #===========================================================================
    def getSelectedFluids(self):
        selectedFluids = []
            
        # for i in range(0, self.fluidsListWidget.count()):
        #     if self.fluidsListWidget.item(i).isSelected():
        #         selectedFluids.append(bblInit.fluidCodes[i].code)
          
        return selectedFluids

    #===========================================================================
    # 
    #===========================================================================
    def lastDateClicked(self, checked):
        if checked:
            self.endDateEdit.setDateTime(self.realEndDate)
        else:
            self.endDateEdit.setDateTime(self.mEndDate)

    #===========================================================================
    # 
    #===========================================================================
    def firstDateClicked(self, checked):
        if checked:
            self.startDateEdit.setDateTime(self.realStartDate)
        else:
            self.startDateEdit.setDateTime(self.mStartDate)
    #===========================================================================
    # 
    #===========================================================================
    def on_mDynamicCheckBox_toggled(self, checked):
        self.startDateEdit.setEnabled(checked)
        self.firstDate.setEnabled(checked)

    #===========================================================================
    # 
    #===========================================================================
    def readSettings(self):
        settings = QSettings()
        self.mStartDate = settings.value("/PDS/production/startDate", QDateTime().currentDateTime())
        self.mEndDate = settings.value("/PDS/production/endDate", QDateTime().currentDateTime())
        self.mSelectedReservoirs = settings.value("/PDS/production/selectedReservoirs")
        self.mPhaseFilter = settings.value("/PDS/production/selectedPhases")
        self.mAddAllWells.setChecked(settings.value("/PDS/production/loadAllWells", 'False') == 'True')
        self.mUpdateWellLocation.setChecked(settings.value("/PDS/production/UpdateWellLocation", 'True') == 'True')
        self.mDynamicCheckBox.setChecked(settings.value("/PDS/production/DynamicProduction", 'False') == 'True')

        self.currentDiagramm = settings.value("/PDS/production/currentDiagramm", "1LIQUID_PRODUCTION")
        
        if self.mPhaseFilter is None:
            self.mPhaseFilter = []
        if self.mSelectedReservoirs is None:
            self.mSelectedReservoirs = []
        
    #===========================================================================
    # 
    #===========================================================================
    def writeSettings(self):
        settings = QSettings()
        settings.setValue("/PDS/production/startDate", self.mStartDate)
        settings.setValue("/PDS/production/endDate", self.mEndDate)
        settings.setValue("/PDS/production/selectedReservoirs", self.mSelectedReservoirs)
        settings.setValue("/PDS/production/selectedPhases", self.mPhaseFilter)

        settings.setValue("/PDS/production/loadAllWells", 'True' if self.mAddAllWells.isChecked() else 'False' )
        settings.setValue("/PDS/production/currentDiagramm", self.currentDiagramm)
        settings.setValue("/PDS/production/UpdateWellLocation", 'True' if self.mUpdateWellLocation.isChecked() else 'False' )
        settings.setValue("/PDS/production/DynamicProduction",  'True' if self.mDynamicCheckBox.isChecked() else 'False')




