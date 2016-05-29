# -*- coding: utf-8 -*-

import unittest
import VereinsFinesse.MainController
import sys
import os
import tempfile
import filecmp


class CompleteTestCases (unittest.TestCase):

    def test_1(self):
        self.do_test_in_directory(u'Test 1')

    def test_umsatzsteuer_nach_finesse(self):
        # Übertrag von VF Buchungen mit Umsatzsteuer nach Finesse.
        # Die erste Buchung ist eine normale Belastung, die zweite storniert diese Belastung.
        self.do_test_in_directory(u'Umsatzsteuer nach Finesse')

    def test_fluggutschrift(self):
        # Übertrag der Gutschrift eines Fluges auf ein Mitgliedskonto. In diesem Fall geht die Steuer auf das
        # Vorsteuerkonto, was wahrscheinlich falsch ist, aber rechnerisch funtkioniert.
        self.do_test_in_directory(u'Fluggutschrift')

    def test_geloeschte_buchung_im_vf(self):
        # Testet das Erzeugen einer Stornobuchung für Finesse, nachdem eine bereits nach Finesse übetragene
        # Buchung im VF gelöscht wurde.
        self.do_test_in_directory(u'Gelöschte Buchung im VF')

    def do_test_in_directory(self, test_dir):
        controller = VereinsFinesse.MainController.MainController()

        # Determine and load configuration file
        config_path = os.path.join(test_dir, u'Config.yaml')
        if not os.path.exists(config_path):
            config_path = u'TestConfig.yaml'

        f = open(config_path, 'rb')
        controller.read_config(f)

        # Import data
        controller.import_vf(os.path.join(test_dir, u'vf_input.csv'))
        controller.import_finesse(os.path.join(test_dir, u'finesse_input.CSV'))

        controller.connectImportedVFBuchungen()
        controller.connectImportedFinesseBuchungen()

        # Export for VF
        expected_path = os.path.join(test_dir, u'vf_expected.csv')
        vf_export_list = controller.finesseBuchungenForExportToVF()
        if len(vf_export_list ) > 0:
            result_path = os.path.join(test_dir, u'vf_result.csv')
            f = open(result_path , 'w+b')
            controller.exportFinesseBuchungenToVF(vf_export_list , f)
            f.close()
            matches = False
            if os.path.exists(expected_path):
                matches = filecmp.cmp(result_path , expected_path)
            self.assertTrue(matches)
            if matches: # else leave it available for inspection
                os.remove(result_path)
        else:
            self.assertFalse(os.path.exists(expected_path))

        # Export for Finesse
        expected_path = os.path.join(test_dir, u'finesse_expected.csv')
        finesse_export_list = controller.vfBuchungenForExportToFinesse()
        if len(finesse_export_list) > 0:
            result_path = os.path.join(test_dir, u'finesse_result.csv')
            f = open(result_path, 'w+b')
            controller.exportVFBuchungenToFinesse(finesse_export_list, f)
            f.close()
            matches = False
            if os.path.exists(expected_path):
                matches = filecmp.cmp(result_path, expected_path)
            self.assertTrue(matches)
            if matches:  # else leave it available for inspection
                os.remove(result_path)
        else:
            self.assertFalse(os.path.exists(expected_path))

if __name__ == '__main__':
    unittest.main()
