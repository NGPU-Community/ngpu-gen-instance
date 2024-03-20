import subprocess
import logging

class Process:
    #just sync calling, eg. result = subprocess.run(['ls', '-l'], capture_output=True, text=True)
    @classmethod
    def launchProcess(cls, cmd:list):
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            logging.info(f"cmd={cmd} succeeded, stdout={result.stdout}")
        else:
            logging.error(f"cmd={cmd} failed, stdout={result.stdout}, stderr={result.stderr}")
        return result.returncode
