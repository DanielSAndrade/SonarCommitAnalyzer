import sys
import http.client
import os
import shutil
import subprocess
import json

def print_(text):
    """ Function to print and flush console. """
    print(text)
    sys.stdout.flush()

def verify_sonar_response(url):
    """ Function to verify SonarQube is running on server. """
    print_(">> Verificando se SonarQube esta em execucao no servidor ...")

    try:
        http_url = url.replace("http://", "")
        sonarhttp = http.client.HTTPConnection(http_url, timeout=10)
        sonarhttp.request("HEAD", "/")
        response = sonarhttp.getresponse()
        ok_text("SonarQube em execucao no servidor {}.".format(url))

    except Exception:
        error_text("SonarQube nao esta em execucao. Commit liberado.")
        system_exit_ok()

def remove_file(file):
    """ Function to remove especific file. """
    if os.path.isfile(file):
        os.remove(file)

def remove_folder(folder):
    """ Function to remove especific folder. """
    if os.path.isdir(folder):
        shutil.rmtree(folder)

def verify_branch_is_merging(git_command):
    """ Function to verify branch is merging. """
    branch_merging = git_command.execute("git status")

    if "All conflicts fixed but you are still merging." in branch_merging:
        ok_text(">> Commit de MERGE. SonarQube nao sera executado.")
        system_exit_ok()

def find_systems_and_keys(repository):
    try:
        file = repository + "Configuracoes.ps1"
        command = ["powershell.exe", ". \"{}\";".format(file), "&obtemListaSolutionsDotNet | ConvertTo-Json"]
        output = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True)
        json_systems = json.loads(output.stdout)
        return json_systems
    except Exception:
        error_text("Nao foi possível encontrar os sistemas no arquivo Configuracoes.ps1.")
        system_exit_ok()    

def write_modules(modules_list, files, system):
    try:
        modules = []
        modules_string = ""
        if system == "MSSNET":
            if len(modules_list) > 0:
                modules_list = sorted(modules_list)
                for module in modules_list:
                    module_files = ",".join({file["File"].replace(module[1] + "/", "") for file in files if file["ID"] == system and module[1] in os.path.dirname(file["File"])})
                    if module_files != "":
                        module_title = "WebServices" if "webservices" in module[0] else module[0].title()
                        module_dict = {
                            "Module": module_title,
                            "BaseDir": "{}.sonar.projectBaseDir={}".format(module_title, module[1]),
                            "Sources": "{}.sonar.sources={}".format(module_title, module_files)
                        }
                        modules.append(module_dict)
                modules_string = "sonar.modules=" + ",".join(sorted({module["Module"] for module in modules})) + "\n"
                for module in modules:
                    modules_string += "\n"
                    modules_string += module["BaseDir"] + "\n"
                    modules_string += module["Sources"] + "\n"          
        return modules_string
    except Exception as err:
        error_text("Nao foi possivel gerar os modulos do SonarQube.")
        system_exit_ok()

def system_exit_block_commit():
    sys.exit(1)

def system_exit_ok():
    sys.exit(0)

def warning_text(text):
    print_("\033[93mWARNING - {}\033[0m\n".format(text))

def ok_text(text):
    print_("\033[92mOK - {}\033[0m\n".format(text))

def error_text(text):
    print_("\033[91mERROR - {}\033[0m\n".format(text))