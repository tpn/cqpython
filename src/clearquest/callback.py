# Copyright 2007 OnResolve Ltd
# $Id$

import sys
import time

class Callback(object):
    def __init__(self, parent):
        self.parent = parent
        self.name = parent.__class__.__name__
        self.current = None
        
        self.failed = 0
        self.created = 0
        self.updated = 0
        self.skipped = 0
        self.expected = 0
        self.progress = -1
        
        self.rate = float(0)
        self.completion = float(0)
        
        self.errors = 0
        self._errors = dict()
        self.error = lambda msg: self._store('error', msg)
        
        self.warnings = 0
        self._warnings = dict()
        self.warning = lambda msg: self._store('warning', msg)
    
    def _store(self, name, details):
        where = self.__dict__['_' + name + 's']
        where.setdefault(self.current, list()).append(details)
        self.__dict__[name + 's'] += 1
    
    def __getitem__(self, name):
        return self.__dict__[name]
    
    def __setitem__(self, name, value):
        self.__dict__[name] = value
        
    def next(self, *args):
        self.progress += 1
        if self.progress == 0:
            if self.expected <= 0:
                raise ValueError, "expected must be greater than 0"
            self.startTime = time.time()
        else:
            self.completion = (float(self.progress)/float(self.expected))*100.0
            try:
                self.rate = self.progress / (time.time() - self.startTime)
            except ZeroDivisionError:
                # This may happen if not enough time has passed in the first
                # couple of iterations.
                self.rate = 0
            
        self.current = args[0] if args else None
    
    def write(self, msg):
        pass
    
    def finished(self):
        if self.expected > 0:
            self.next()
            self.write('\n')

class ConsoleCallback(Callback):
    format = '%s: created: %d, updated: %d, skipped: %d, failed: %d, ' \
             'errors: %d, warnings: %d [%%%3.2f, %.2f items/sec]'
        
    def write(self, msg):
        sys.stdout.write(msg)
          
    def next(self, *args):
        Callback.next(self, *args)
            
        # The PyDev Eclipse debugger doesn't handle '\b' as backspace, it just
        # prints lots of chunky blocks instead, so don't bother with this.
        if not 'pydevd' in sys.modules:
            self.write('\b' * 132)
            
        self.write(self.format % (self.name, self.created, self.updated, 
                                  self.skipped, self.failed, self.errors,
                                  self.warnings, self.completion, self.rate))
        
        if 'pydevd' in sys.modules:
            self.write('\n')
    
    def _report(self, name):
        info = getattr(self, '_' + name)
        if info:
            self.write('\n%s:' % name)
            for (id, backtrace) in info.items():
                self.write('\n%s:\n\t%s' % \
                    (id, '\n\t'.join([
                        b.replace('\n', '\n\t') for b in backtrace 
                    ]))
                )
            self.write('\n')
    
    def finished(self):
        Callback.finished(self)
        self._report('warnings')
        self._report('errors')
        
