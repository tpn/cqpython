
import os
import sys
import time
import signal
if not 'twisted.internet.reactor' in sys.modules:
    from twisted.internet import iocpreactor
    iocpreactor.proactor.install()

from ipython1.kernel.scripts import ipcluster
from ipython1.kernel.api import RemoteController
from subprocess import Popen


def distributed(f):
    def newf(*_args, **_kwds):
        f(_args, _kwds)
        self = _args[0]
        if not 'distributed' in _kwds:
            return
        d = self.__dict__
        if not 'cluster' in d:
            cluster = d['cluster'] = Cluster(_kwds.get('clusterSize', 4))
            rc = d['rc'] = d['cluster'].remoteController 
        
        stmt = []
        module = self.__class__.__module__
        name = self.__class__.__name__
        if not '__main__' == module:
            stmt += 'from %s import %s' % (module, name)
        stmt += 'this = %s()' % name
        try:
            rc.executeAll(stmt)
        except:
            cluster.cleanup()
            raise
        return
    return newf

stop = lambda pid: os.kill(pid, signal.SIGINT)
kill = lambda pid: os.kill(pid, signal.SIGTERM)    

class Cluster(object):
    
    def __init__(self, size=2, **kwds):
        self.size = size
        self.name = kwds.get('name', 'cluster')
        self.logdir = kwds.get('logdir', os.getcwd())
        self.logfile = '%s-' % self.name
        self.controller = Popen(['ipcontroller', '--logfile',self.logfile])
        self.engineLogFile = '%s%s-' % (self.logfile, self.controller.pid)
        
        self.engines = [ Popen(['ipengine', '--logfile', self.engineLogFile]) \
                            for i in range(size) ]
        self.eids = [ e.pid for e in self.engines ]
        self.remoteController = RemoteController(('127.0.0.1', 10105))
    
    def numAlive(self):
        retcodes = [ self.controller.poll() ] + \
                   [ e.poll() for e in self.engines ]
        return retcodes.count(None)

    def __del__(self):
        self.cleanup()
    
    def _cleanup(self, method):
        for e in self.engines:
            if e.poll() is None:
                method(e.pid)
        if self.controller.poll() is None:
            method(self.controller.pid)
        
    def cleanup(self):
        self._cleanup(stop)
        for i in range(4):
            time.sleep(i+2)
            if self.numAlive() == 0:
                break
            self._cleanup(kill)
            if self.numAlive() == 0:
                break
        else:
            zombies = []
            if self.controller.returncode is None:
                zombies.append(self.controller.pid)
            zombies += [ e for e in self.engines if e.returncode is None ]
            print "zombies: ", ', '.join(map(str, zombies))
            
                
#class DistributedAdminSession(AdminSession):
#    def __init__(self, size):
#        self.size = size
#        AdminSession.__init__(self)
#        self.cluster = Cluster(size)
#        self.rc = self.cluster.remoteController
#        self.rc.executeAll("""
#            from onresolve.clearquest.api import AdminSession
#            this = AdminSession()
#        """)
#    
#    def Logon(self, *args):
#        AdminSession.Logon(self, *args)
#        cmd = 'this.Logon(%s)' % ", ".join([ "'" + a + "'" for a in args ])
#        print "excuting: %s" + cmd
#        self.rc.execute(cmd)
    
    
        
        
        