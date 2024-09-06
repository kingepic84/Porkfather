import psutil,subprocess, sys
for process in psutil.process_iter():
    if process.name() == "python3 Porkbot.py" or process.name() == "py Porkbot.py":
        process.kill()
        process.wait()
git = subprocess.run(["git", "pull"], stdout=sys.stdout, stderr=sys.stderr)
if git.check_returncode():
    runpy = subprocess.Popen(["nohup" ,"python3" ,"Porkbot.py"], stdout=sys.stdout, stderr=sys.stderr)
print('Porkfather Restarted')
