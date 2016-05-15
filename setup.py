# Setup for py2exe

from distutils.core import setup
import py2exe

setup(console=['vf.py'],
      options={"py2exe":{
          "packages":['VereinsFinesse', 'yaml']
      }
   }
)

#sys.path.append("C:\\Program Files\\Microsoft Visual Studio 9.0\\VC\\redist\\x86\\Microsoft.VC90.CRT")