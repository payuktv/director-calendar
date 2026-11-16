"""Exercise the real entry point, daily backup and relaunch in separate processes."""
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic, sleep


def test_real_entry_point_creates_daily_copy_and_activates_owner_on_relaunch(tmp_path):
    folder = tmp_path / 'Тестовый профиль'
    folder.mkdir()
    script = r'''
import os
from pathlib import Path
from PySide6.QtCore import QTimer
from director_control import ui
root=Path(os.environ['DIRECTOR_CONTROL_DATA_DIR'])
initialize=ui.MainWindow.__init__
activate=ui.MainWindow.activateWindow
def init(self,*args,**kwargs):
    initialize(self,*args,**kwargs)
    def tick():
        (root/'ready').touch()
        if (root/'stop').exists() and not self.backup_panel.busy and not self.mail_panel.busy:
            self.close()
    self.test_timer=QTimer(self)
    self.test_timer.timeout.connect(tick)
    self.test_timer.start(25)
def activated(self):
    (root/'activated').write_text('owner')
    activate(self)
ui.MainWindow.__init__=init
ui.MainWindow.activateWindow=activated
raise SystemExit(ui.run_app())
'''
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen', DIRECTOR_CONTROL_DATA_DIR=str(folder))
    project = Path(__file__).resolve().parents[1]
    owner = subprocess.Popen([sys.executable, '-c', script], cwd=project, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    def wait_for(path):
        deadline = monotonic()+15
        while monotonic() < deadline and owner.poll() is None:
            if path.exists():
                return
            sleep(.025)
        raise AssertionError('Application did not create '+str(path))
    try:
        wait_for(folder/'ready')
        relaunched = subprocess.run([sys.executable, str(project/'main.pyw')], cwd=project, env=env,
                                   capture_output=True, text=True, timeout=15)
        assert relaunched.returncode == 0, relaunched.stderr
        wait_for(folder/'activated')
        (folder/'stop').touch()
        out, err = owner.communicate(timeout=15)
        assert owner.returncode == 0, out+err
        assert len(list((folder/'backups').glob('auto-*.db'))) == 1
        assert not list(folder.glob('*.lock'))
    finally:
        (folder/'stop').touch()
        if owner.poll() is None:
            try:
                owner.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                owner.kill()
                owner.communicate(timeout=5)
