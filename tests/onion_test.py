import unittest

import os

from . import OBSLocal

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')

class TestOnion(unittest.TestCase):

    def setup_onion(self):
        wf = OBSLocal.StagingWorkflow()
        devel1 = wf.create_project("Devel1")
        devel2 = wf.create_project("Devel2")
        devel2.update_meta(with_repo=True)
        first = wf.create_project("Onion1")
        first.update_meta(with_repo=True)
        second = wf.create_project("Onion2", project_links=["Onion1"])
        second.update_meta(with_repo=True)

        self.onioned_package(first, second, devel1, devel2)

        pkg2_devel = OBSLocal.Package("pkg2", devel1)
        pkg2 = OBSLocal.Package("pkg2", first, devel_project="Devel1")

        mkdud_devel = OBSLocal.Package("mkdud", devel1)
        mkdud = OBSLocal.Package("mkdud", first, devel_project="Devel1")
        self.create_mkdud(mkdud)

        return wf

    def onioned_package(self, first, second, devel1, devel2):
        self.devel_old_package = OBSLocal.Package('blowfish', devel1)
        self.old_package = OBSLocal.Package('blowfish', first, devel_project="Devel1")
        self.devel_new_package = OBSLocal.Package('blowfish', devel2)
        self.new_package = OBSLocal.Package('blowfish', second, devel_project="Devel2")

        blowfish_spec = os.path.join(FIXTURES, 'packages', 'blowfish', 'blowfish.spec')
        with open(blowfish_spec) as f:
            self.devel_new_package.create_commit(filename='blowfish.spec', text=f.read())

        blowfish_changes = os.path.join(FIXTURES, 'packages', 'blowfish', 'blowfish.changes')
        with open(blowfish_changes) as f:
            self.devel_new_package.create_commit(filename='blowfish.changes', text=f.read())

        self.devel_new_package.create_file(filename='blowfish-1.tar.gz')

    def create_mkdud(self, pkg):
        spec = os.path.join(FIXTURES, 'packages', 'mkdud', 'mkdud.spec')
        with open(spec) as f:
            pkg.create_commit(filename='mkdud.spec', text=f.read())

        changes = os.path.join(FIXTURES, 'packages', 'mkdud', 'mkdud.changes')
        with open(changes) as f:
            pkg.create_commit(filename='mkdud.changes', text=f.read())

        tarball = os.path.join(FIXTURES, 'packages', 'mkdud', 'mkdud-1.52.tar.xz')
        with open(changes) as f:
            pkg.create_commit(filename='mkdud-1.52.tar.xz', text=f.read())

    def test_onion(self):
        wf = self.setup_onion()
        wf.submit_package(package=self.devel_new_package, project="Onion2")
        breakpoint()
        print(wf)
