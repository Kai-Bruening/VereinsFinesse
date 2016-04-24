# Setup for py2exe

from distutils.core import setup
import py2exe

setup(console=['vf.py'],
      options={"py2exe":{
          "packages":['VereinsFinesse', 'yaml']
      }
   }
)
