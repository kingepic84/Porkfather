import psutil,subprocess,sys
from subprocess import DEVNULL
for process in psutil.process_iter():
    if "python3 Porkbot.py" in process.name():
        process.kill()
        process.wait()
git = subprocess.run(["git", "pull"], stdout=sys.stdout, stderr=sys.stderr)
pork = subprocess.Popen(["nohup python3 Porkbot.py"], stdout=DEVNULL, stderr=sys.stdout, shell=True)
print("Porkfather Restarted")

