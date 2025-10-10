#! python3

# PYTHON STANDARD LIBRARY IMPORTS ---------------------------------------------
import threading
import time
import hashlib
from typing import Optional, Callable, Any
import uuid

# RHINO AND GH RELATED IMPORTS ------------------------------------------------
import System  # type: ignore[reportMissingImport] # NOQA
import Grasshopper  # type: ignore[reportMissingImport] # NOQA
import Rhino  # type: ignore[reportMissingImport] # NOQA
import scriptcontext as sc  # type: ignore[reportMissingImport] # NOQA

# GHENV COMPONENT SETTINGS ----------------------------------------------------
ghenv.Component.Name = 'AsyncPrimeCalculator'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.NickName = 'AsyncPrime'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Category = 'DDU_CSC'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.SubCategory = '0 Development'  # type: ignore[reportUnedfinedVariable] # NOQA
ghenv.Component.Description = (  # type: ignore[reportUnedfinedVariable] # NOQA
    'Async prime calculator - calculates the nth prime number. '
    'Updates component only when work is complete via callback. '
    'Auto-resets when inputs change.'
)


def updateComponent():
    """Updates this component using callback mechanism"""
    
    # Define callback action
    def callBack(e):
        ghenv.Component.ExpireSolution(False)
        
    # Get grasshopper document
    ghDoc = ghenv.Component.OnPingDocument()
    
    # Schedule this component to expire
    ghDoc.ScheduleSolution(1, Grasshopper.Kernel.GH_Document.GH_ScheduleDelegate(callBack))


class AsyncWorker:
    """Async worker that calls back when work is complete"""
    
    def __init__(self, worker_id: str, callback_function: Callable):
        self.worker_id = worker_id
        self.callback = callback_function
        self.cancelled = False
        self.result = None
        self.error = None
        self.thread = None
        self.completed = False
        
    def start_work(self, work_function: Callable, *args, **kwargs):
        """Start work in background thread"""
        self.cancelled = False
        self.result = None
        self.error = None
        self.completed = False
        
        def work_wrapper():
            try:
                # Do the work
                self.result = work_function(self, *args, **kwargs)
                self.completed = True
                
                # Store results in sticky for retrieval
                iguid = str(ghenv.Component.InstanceGuid)
                sc.sticky[iguid + "__Result"] = self.result
                sc.sticky[iguid + "__Error"] = None
                sc.sticky[iguid + "__Completed"] = True
                
                # Call back to update component
                self.callback()
                
            except Exception as e:
                self.error = e
                self.completed = True
                
                # Store error in sticky
                iguid = str(ghenv.Component.InstanceGuid)
                sc.sticky[iguid + "__Result"] = None
                sc.sticky[iguid + "__Error"] = str(e)
                sc.sticky[iguid + "__Completed"] = True
                
                # Call back to update component
                self.callback()
        
        self.thread = threading.Thread(target=work_wrapper, daemon=True)
        self.thread.start()
    
    def cancel(self):
        """Cancel the worker"""
        self.cancelled = True
    
    def is_done(self):
        """Check if work is complete"""
        if self.thread is None:
            return True
        return not self.thread.is_alive() and self.completed


class CSC_AsyncPrimeCalculator(Grasshopper.Kernel.GH_ScriptInstance):
    """
    Async prime calculator component using callback pattern with auto-reset
    
    Author: Max Benjamin Eschenbach
    License: MIT License
    Version: 251010
    """
    
    def __init__(self):
        super().__init__()
        self.Component = ghenv.Component
        self.InputParams = self.Component.Params.Input
        self.OutputParams = self.Component.Params.Output
        
        # Define sticky keys for persistent data storage
        self.iguid = str(ghenv.Component.InstanceGuid)
        self.worker_key = self.iguid + "__Worker"
        self.result_key = self.iguid + "__Result"
        self.error_key = self.iguid + "__Error"
        self.completed_key = self.iguid + "__Completed"
        self.inputs_hash_key = self.iguid + "__InputsHash"
        
    def _addRemark(self, msg: str = ''):
        rml = self.Component.RuntimeMessageLevel.Remark
        self.AddRuntimeMessage(rml, msg)
    
    def _addWarning(self, msg: str = ''):
        rml = self.Component.RuntimeMessageLevel.Warning
        self.AddRuntimeMessage(rml, msg)
    
    def _addError(self, msg: str = ''):
        rml = self.Component.RuntimeMessageLevel.Error
        self.AddRuntimeMessage(rml, msg)
    
    def _create_inputs_hash(self, nth_prime: int):
        inputs_string = f"{nth_prime}"
        return hashlib.md5(inputs_string.encode()).hexdigest()

    def _inputs_changed(self, nth_prime: int):
        current_hash = self._create_inputs_hash(nth_prime)
        stored_hash = sc.sticky.get(self.inputs_hash_key)
        if stored_hash != current_hash:
            sc.sticky[self.inputs_hash_key] = current_hash
            return True
        return False
    
    def _empty_output(self):
        return Grasshopper.DataTree[System.Object]()
    
    def _reset_async_work(self):
        """Reset all async work data"""
        sc.sticky[self.worker_key] = None
        sc.sticky[self.result_key] = None
        sc.sticky[self.error_key] = None
        sc.sticky[self.completed_key] = False
        
        # Cancel any running worker
        worker = sc.sticky.get(self.worker_key)
        if worker:
            worker.cancel()
    
    def _calculate_primes(self, worker: AsyncWorker, nth_prime: int):
        """Prime calculation - no progress reporting during work"""
        # Check for cancellation
        if worker.cancelled:
            return None
            
        count = 0
        a = 2
        
        while count < nth_prime:
            # Check for cancellation
            if worker.cancelled:
                return None
                
            b = 2
            prime = 1  # to check if found a prime
            
            while b * b <= a:
                # Check for cancellation
                if worker.cancelled:
                    return None
                    
                if a % b == 0:
                    prime = 0
                    break
                b += 1
            
            if prime > 0:
                count += 1
            a += 1
        
        return a - 1
    
    def _useless_cycles(self, worker: AsyncWorker, max_iterations: int):
        """Useless cycles - no progress reporting during work"""
        # Check for cancellation
        if worker.cancelled:
            return None
            
        for i in range(max_iterations + 1):
            # Check for cancellation
            if worker.cancelled:
                return None
            
            # Simulate work
            for j in range(100):
                if worker.cancelled:
                    return None
                # Do some CPU work
                _ = sum(range(100))
        
        return f"Worker {worker.worker_id} completed {max_iterations} cycles"
    
    def RunScript(self, NthPrime: int, Reset: bool):
        """
        Prime-only async version.
        - Inputs: NthPrime (int), Reset (bool)
        - Output: empty GH tree until result is ready; final output is the prime (int)
        """

        # Auto-reset on input change or first run, or manual reset
        inputs_changed = self._inputs_changed(NthPrime)
        if Reset or inputs_changed or self.completed_key not in sc.sticky:
            self._reset_async_work()
            self.Component.Message = "Inputs changed - resetting..." if inputs_changed else "Reset"
            return self._empty_output()

        # If completed, return stored result
        if sc.sticky.get(self.completed_key, False):
            result = sc.sticky.get(self.result_key)
            error = sc.sticky.get(self.error_key)
            if error:
                self.Component.Message = f"Error: {str(error)}"
                return self._empty_output()
            self.Component.Message = "Work completed!"
            return result  # final computed prime (int)

        # If running, do not re-trigger; just keep output empty
        worker = sc.sticky.get(self.worker_key)
        if worker and not worker.is_done():
            self.Component.Message = "Work in progress..."
            return self._empty_output()

        # Start new prime computation
        try:
            nth_prime = max(1, min(10000, NthPrime))  # adjust cap if desired

            self.Component.Message = f"Calculating {nth_prime}th prime..."
            worker_id = f"worker-{uuid.uuid4().hex[:8]}"
            worker = AsyncWorker(worker_id, updateComponent)
            sc.sticky[self.worker_key] = worker

            work_function = lambda w: self._calculate_primes(w, nth_prime)
            worker.start_work(work_function)

            # Keep output empty until callback triggers recompute and result is ready
            return self._empty_output()

        except Exception as e:
            self._addError(f"Async work failed: {str(e)}")
            self.Component.Message = f"Error: {str(e)}"
            sc.sticky[self.error_key] = str(e)
            sc.sticky[self.completed_key] = True
            return self._empty_output()