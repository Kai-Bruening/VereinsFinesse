# -*- coding: utf-8 -*-

from unittest import TestCase
import VereinsFinesse.MainController
import VereinsFinesse.CheckDigit
import tempfile
import filecmp
import sys
import os
import codecs
from decimal import Decimal


class TestMainController (TestCase):
    # test_run(self):
    #  pass

    def test_import_vf(self):
        controller = VereinsFinesse.MainController.MainController()
        f = open('TestConfig.yaml', 'rb')
        controller.read_config (f)
        controller.import_vf('VereinsfliegerTestExport.csv')
        self.assertEqual(len(controller.vf_buchungen), 6)
        self.assertEqual(len(controller.vf_buchungenImportedFromFinesse), 1)
        self.assertEqual(len(controller.vf_buchungenForExportToFinesse), 5)

        b = controller.vf_buchungen[0]
        self.assertEqual (b.gegen_konto, 5155)
        self.assertEqual (b.gegen_konto_kostenstelle, 222)
        self.assertEqual (b.konto, 11564)
        self.assertEqual (b.betrag, Decimal (0))
        self.assertEqual (b.steuer_konto, 1876)
        self.assertEqual (b.mwst_satz, Decimal ('7'))
        self.assertEqual (b.steuerfall.code, 2)
        self.assertEqual (b.buchungstext, u'Gebührenabrechnung')

        b = controller.vf_buchungen[3]
        self.assertEqual (b.gegen_konto, 5155)
        self.assertIsNone (b.gegen_konto_kostenstelle)
        self.assertEqual (b.konto, 11564)
        self.assertEqual (b.betrag, Decimal ('-2.20'))
        self.assertEqual (b.steuer_konto, 1876)
        self.assertEqual (b.mwst_satz, Decimal ('7'))
        self.assertEqual (b.steuerfall.code, 2)
        self.assertEqual (b.buchungstext, u'Gebührenabrechnung')

        # zahlungseingaengeByBelegnummer = controller.vf_belegarten[u'ZE']
        # self.assertEqual(len(zahlungseingaengeByBelegnummer), 1)
        # zahlungseingaenge = zahlungseingaengeByBelegnummer[4711]
        # self.assertEqual(len(zahlungseingaenge), 1)
        # b = zahlungseingaenge[0]
        # self.assertEqual(b.KontoHaben, 11564)
        # self.assertEqual(b.KontoSoll, 1200)
        # self.assertEqual(b.BetragHaben, Decimal('63.36'))
        # self.assertEqual(b.BetragSoll, Decimal('63.36'))
        # self.assertIsNone(b.SteuerKonto)
        # self.assertEqual(b.mwst_satz, Decimal('0'))
        # self.assertEqual(b.Buchungstext, u'Kontoausgleich SEPA')

    def test_import_vf_with_errors(self):
        controller = VereinsFinesse.MainController.MainController()
        f = open(u'TestConfig.yaml', 'rb')
        controller.read_config (f)
        controller.import_vf(u'VereinsfliegerFehlerhafterExport.csv')
        self.assertEqual(len(controller.vf_buchungen), 1)
        f = tempfile.NamedTemporaryFile(mode='w+b', prefix='output', suffix='.txt', delete=False)
        temp_path = f.name
        #print f.name
        sys.stdout = codecs.getwriter('windows-1252')(f)
        controller.report_errors()
        f.flush()
        f.close()
        self.assertTrue(filecmp.cmp(temp_path, u'VereinsfliegerFehlerhafterExport.txt'))
        os.remove(temp_path)

    def test_import_finesse(self):
        controller = VereinsFinesse.MainController.MainController()
        f = open (u'TestConfig.yaml', 'rb')
        controller.read_config (f)
        controller.import_finesse(u'FinesseTestExport.csv')
        self.assertEqual (len (controller.finesse_buchungen), 8)
        self.assertEqual (len (controller.finesse_buchungen_originally_imported_from_vf), 5)
       # self.assertEqual (len (controller.finesse_buchungenForExportToVF), 3)

        # zahlungseingaengeByJournalnummer = controller.finesse_Journale[u'Lastschriften-import']
        # self.assertEqual(len(zahlungseingaengeByJournalnummer), 2)
        #
        # zahlungseingaenge = zahlungseingaengeByJournalnummer[4711]
        # self.assertEqual(len(zahlungseingaenge), 1)
        # b = zahlungseingaenge[0]
        # self.assertEqual(b.KontoHaben, 11564)
        # self.assertEqual(b.KontoSoll, 1200)
        # self.assertEqual(b.BetragHaben, Decimal('63.36'))
        # self.assertEqual(b.BetragSoll, Decimal('63.36'))
        # self.assertIsNone(b.SteuerKonto)
        # # self.assertEqual(b.mwst_satz, Decimal('0'))
        # self.assertEqual(b.Buchungstext, u'Kontoausgleich SEPA')
        #
        # zahlungseingaenge = zahlungseingaengeByJournalnummer[4712]
        # self.assertEqual(len(zahlungseingaenge), 1)
        # b = zahlungseingaenge[0]
        # self.assertEqual(b.KontoHaben, 11564)
        # self.assertEqual(b.KontoSoll, 1200)
        # self.assertEqual(b.BetragHaben, Decimal('101.10'))
        # self.assertEqual(b.BetragSoll, Decimal('101.10'))
        # self.assertIsNone(b.SteuerKonto)
        # # self.assertEqual(b.mwst_satz, Decimal('0'))
        # self.assertEqual(b.Buchungstext, u'AVIA Lastschrift')

    def test_import_finesse_with_errors(self):
        controller = VereinsFinesse.MainController.MainController()
        f = open (u'TestConfig.yaml', 'rb')
        controller.read_config (f)
        controller.import_finesse(u'FinesseFehlerhafterExport.CSV')
        self.assertEqual (len (controller.finesse_buchungen), 3)
        f = tempfile.NamedTemporaryFile (mode='w+b', prefix='output', suffix='.txt', delete=False)
        temp_path = f.name
        #print f.name
        sys.stdout = codecs.getwriter('windows-1252')(f)
        controller.report_errors()
        f.flush()
        f.close()
        self.assertTrue(filecmp.cmp(temp_path, u'FinesseFehlerhafterExport.txt'))
        os.remove(temp_path)
        pass

    def test_connectImportedVFBuchungen(self):
        controller = self.prepare_controller()
        controller.connectImportedVFBuchungen ()
        self.assertEqual (controller.vf_buchungen[5].original_buchung, controller.finesse_buchungen[0])
        self.assertEqual (controller.finesse_buchungen[0].kopierte_buchung, controller.vf_buchungen[5])
        self.assertEqual (len (controller.fehlerhafte_vf_buchungen), 0)

    def test_connectImportedFinesseBuchungen(self):
        controller = self.prepare_controller()
        controller.connectImportedFinesseBuchungen ()

        self.assertEqual (controller.finesse_buchungen[2].original_buchung, controller.vf_buchungen[0])
        self.assertEqual (controller.vf_buchungen[0].kopierte_buchungen, [controller.finesse_buchungen[2]])

        self.assertEqual (controller.finesse_buchungen[3].original_buchung, controller.vf_buchungen[1])
        self.assertEqual (controller.finesse_buchungen[4].original_buchung, controller.vf_buchungen[1])
        self.assertEqual (controller.vf_buchungen[1].kopierte_buchungen,
                          [controller.finesse_buchungen[3], controller.finesse_buchungen[4]])

        self.assertEqual (controller.finesse_buchungen[5].original_buchung, controller.vf_buchungen[3])
        self.assertEqual (controller.vf_buchungen[3].kopierte_buchungen, [controller.finesse_buchungen[5]])

        self.assertEqual (len (controller.fehlerhafte_finesse_buchungen), 0)

    def test_finesseBuchungenForExportToVF(self):
        controller = self.prepare_controller()
        controller.connectImportedVFBuchungen ()
        export_list = controller.finesseBuchungenForExportToVF ()
        self.assertEqual (len (export_list), 2)
        self.assertEqual (int(VereinsFinesse.CheckDigit.check_and_strip_checkdigit(unicode(export_list[0].vf_belegnummer))),
                          controller.finesse_buchungen[1].finesse_journalnummer)

    def test_vfBuchungenForExportToFinesse(self):
        controller = self.prepare_controller()
        controller.connectImportedFinesseBuchungen()
        export_list = controller.vfBuchungenForExportToFinesse()
        self.assertEqual (len (export_list), 4)
        self.assertEqual (export_list[1].vf_nr, controller.vf_buchungen[2].vf_nr)

    def test_exportFinesseBuchungenToVF(self):
        controller = self.prepare_controller()
        controller.connectImportedVFBuchungen ()
        export_list = controller.finesseBuchungenForExportToVF ()
        result_path = u'VereinsfliegerTestResult.csv'
        f = open(result_path, 'w+b')
        controller.exportFinesseBuchungenToVF (export_list, f)
        f.close()
        matches = filecmp.cmp(result_path, u'VereinsfliegerTestImport.csv')
        self.assertTrue (matches)
        if matches:  # else leave it available for inspection
           os.remove(result_path)

    def test_exportVFBuchungenToFinesse(self):
        controller = self.prepare_controller()
        controller.connectImportedFinesseBuchungen ()
        export_list = controller.vfBuchungenForExportToFinesse ()
        result_path = u'FinesseTestResult.csv'
        f = open(result_path, 'w+b')
        controller.exportVFBuchungenToFinesse (export_list, f)
        f.close()
        matches = filecmp.cmp(result_path, u'FinesseTestImport.csv')
        self.assertTrue (matches)
        if matches:  # else leave it available for inspection
            os.remove(result_path)

    def test_read_config(self):
        controller = VereinsFinesse.MainController.MainController()
        f = open(u'TestConfig.yaml', 'rb')
        controller.read_config(f)
        self.assertIn(u'steuerfaelle', controller.config)
        steuercodes = controller.config[u'steuerfaelle']
        self.assertEqual(len (steuercodes), 9)
        code1 = steuercodes[1]
        self.assertEqual(code1.code, 1)
        self.assertEqual(code1.konto_finesse, 1775)
        self.assertEqual(code1.bezeichnung, u'Umsatzsteuerfrei')
        self.assertEqual(code1.ust_satz, 0)
        self.assertEqual(controller.steuer_configuration.steuerfall_for_vf_steuerkonto_and_steuersatz(1775, 0), code1)

        self.assertFalse(controller.ausgenommene_konten_vf_nach_finesse.enthaelt_konto(999))
        self.assertTrue(controller.ausgenommene_konten_vf_nach_finesse.enthaelt_konto(1000))
        self.assertTrue(controller.ausgenommene_konten_vf_nach_finesse.enthaelt_konto(1009))
        self.assertFalse(controller.ausgenommene_konten_vf_nach_finesse.enthaelt_konto(1010))
        self.assertTrue(controller.ausgenommene_konten_vf_nach_finesse.enthaelt_konto(9008))

    def prepare_controller(self):
        controller = VereinsFinesse.MainController.MainController()
        f = open (u'TestConfig.yaml', 'rb')
        controller.read_config (f)
        controller.import_vf(u'VereinsfliegerTestExport.csv')
        controller.import_finesse(u'FinesseTestExport.csv')
        return controller
