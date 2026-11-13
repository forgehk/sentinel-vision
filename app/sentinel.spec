# PyInstaller spec: one folder, four programs.
#
#     pyinstaller --noconfirm --clean sentinel.spec
#
# The result is dist/SentinelVision/ with SentinelOffice, SentinelShop, SentinelHome and SentinelExam in it.
# They share a single copy of Python, OpenCV and ONNX Runtime (the _internal folder), so the download is one
# runtime plus four small launchers rather than four full copies. models/, samples/, zones/ and fonts/ are
# copied in beside them by the build script; the programs read those folders at start.
import os, sys

HERE = os.path.abspath(SPECPATH)
APPS = ['SentinelOffice', 'SentinelShop', 'SentinelHome', 'SentinelExam']

a = Analysis([os.path.join(HERE, name + '.py') for name in APPS],
             pathex=[HERE, os.path.join(HERE, '..', 'pipeline')],
             excludes=['torch', 'torchvision', 'scipy', 'matplotlib', 'pandas', 'onnx', 'IPython', 'pytest'])
pyz = PYZ(a.pure)

exes = []
for name in APPS:
    scripts = [s for s in a.scripts if s[0] == name or s[0] not in APPS]        # this program's entry script plus PyInstaller's own start-up hooks
    exes.append(EXE(pyz, scripts, [], exclude_binaries=True, name=name, console=False,
                    icon=os.path.join(HERE, 'assets', 'sentinel.ico') if sys.platform == 'win32' else None))

COLLECT(*exes, a.binaries, a.datas, name='SentinelVision')
