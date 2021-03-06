import os
import subprocess
import sys
import webbrowser
import git
import utils
import time
from config import ConfigTool
from itertools import chain

class CommitAnalyzer(object):
    """ Class to analyze commit. """
    def __init__(self):
        absolute_file_path = os.path.abspath(__file__).replace(os.path.basename(__file__), "")
        config = ConfigTool(absolute_file_path + "\\config.ini")

        sonarconfigs = config.configsectionmap("Sonar")
        self.sonar_scanner = sonarconfigs["scanner"]
        self.sonar_server = sonarconfigs["url"]
        self.sonar_login = sonarconfigs["login"]
        self.sonar_password = sonarconfigs["password"]
        self.sonar_folder = sonarconfigs["folder"]
        self.sonar_template = sonarconfigs["template"]

        repositoryconfig = config.configsectionmap("Repository")
        self.base_repository = repositoryconfig["repository"]
        self.base_ci = repositoryconfig["ci"]

        scanstatus = config.configsectionmap("Status")
        self.scan_status = scanstatus["on"].lower() == "true"

        self.git_repository = git.Repo(self.base_repository)
        self.git_command = git.Git(self.base_repository)
        self.systems_and_keys = utils.find_systems_and_keys(self.base_ci)

        self.modules = config.configsectionmap("Modules")

        self.files = []
        self.systems = []
        self.scanner_error = False

    def find_modifed_systems_in_file_folders(self, file):
        """ Function to find systems in file folders. """
        try:
            file = file.a_path
            file_folders = file.split("/")
            folder = self.base_repository + file.replace("/" + file_folders[len(file_folders)-1], "")

            for i in range(len(file_folders)-1, 0, -1):
                folder = folder.replace("/" + file_folders[i], "")
                for _, _, files in os.walk(folder):
                    for file_system in files:
                        if file_system.endswith(".sln"):
                            return file_system

        except Exception:
            utils.error_text("Nao foi possivel encontrar os sistemas a partir dos arquivos modificados.")
            utils.system_exit_ok()

    def find_modified_systems(self, file):
        """ Function to find systems. """
        try:
            solution = self.find_modifed_systems_in_file_folders(file)
            system = list(system for system in self.systems_and_keys if solution.upper() in system["Solution"].upper())[0]
            solution_path = system["Solution"].upper().replace(solution.upper(), "")
            solution = solution.replace(".sln", "")
            if str(solution_path.replace("\\", "/")).upper() in file.a_path.upper():
                file_dictionary = {"ID": system["ID"], "System": solution, "File": file.a_path}
                return file_dictionary            

        except Exception:
            utils.error_text("Nao foi possivel encontrar os sistemas a partir dos arquivos modificados.")
            utils.system_exit_ok()

    def find_modified_files(self):
        """ Function to find modified files. """
        utils.print_(">> Analisando arquivos C# no stage ...")        

        try:
            modified_files = self.git_repository.head.commit.diff()

            if not modified_files:
                utils.ok_text("Nenhum arquivo alterado.")
                utils.system_exit_ok()            

            for file in modified_files:
                _, file_extension = os.path.splitext(file.a_path)
                if file.change_type != "D" and file_extension.lower() == ".cs":
                    dictionary = self.find_modified_systems(file)
                    self.files.append(dictionary)            

            if len(self.files) == 0:
                utils.ok_text("Nenhum arquivo alterado.")
                utils.system_exit_ok()

            self.systems = {file["ID"] for file in self.files}
            self.systems = sorted(self.systems)     

            for system in self.systems:
                index = list(self.systems).index(system)+1
                utils.print_("{}. Sistema: {}".format(index, system))
                files = {file["File"] for file in self.files if file["ID"] == system}
                files = sorted(files)
                for file in files:
                    utils.print_(" - " + file)
            utils.print_("")

        except Exception:
            utils.error_text("Nao foi possivel encontrar os arquivos modificados no stage.")
            utils.system_exit_ok()

    def remove_configuration_file(self, system):
        """ Function to remove sonar configuration file. """
        utils.print_(">> Removendo arquivo de configuracao ...")        

        try:
            utils.remove_file(self.sonar_folder + "{}.sonarsource.properties".format(system))
            utils.ok_text("Arquivo {}.sonarsource.properties removido com sucesso.".format(system))

        except Exception:
            utils.error_text("Nao foi possivel remover o arquivo de configuracao do sistema {}".format(system))
            utils.system_exit_ok()

    def run_sonar(self, system):
        """ Function to run sonar-scanner. """              
        utils.print_(">> Executando SonarQube no sistema {} ...".format(system))  

        try:            
            command = self.sonar_scanner + " -D project.settings={}{}.sonarsource.properties".format(self.sonar_folder, system)
            output = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True, encoding="utf-8")

            if "EXECUTION FAILURE" in output.stdout:
                utils.error_text("Nao foi possivel executar o SonarQube no sistema {}".format(system))
                utils.system_exit_ok()

            if "major" in output.stdout or "critical" in output.stdout:
                webbrowser.open(self.sonar_folder + "issues-report/{}/issues-report-{}.html".format(system, system), new=2)
                utils.ok_text("Relatorio disponibilizado no navegador.")
                self.scanner_error = True
            else:
                utils.ok_text("Analise concluida.")

        except Exception:
            utils.error_text("Nao foi possivel executar o SonarQube no sistema {}".format(system))
            utils.system_exit_ok()

        self.remove_configuration_file(system)

    def preparing_sonar(self, system):
        """ Function to preparing sonar-scanner execution. """
        utils.print_(">> Preparando execucao do SonarQube no sistema {} ...".format(system))   

        language = list({item["Language"] for item in self.systems_and_keys if system.upper() in item["ID"].upper()})[0]
        files = ",".join({file["File"] for file in self.files if file["ID"] == system})
        modules = utils.write_modules(self.modules.items(), self.files, system)

        replacements = {
            "{url}": self.sonar_server,
            "{login}": self.sonar_login,
            "{password}": self.sonar_password,
            "{repository}": self.base_repository,
            "{system}": system,
            "{branch}": self.git_repository.active_branch.name,
            "{sources}": "sonar.sources=" + files,
            "{files}": files,
            "{language}": language,
            "{modules}": modules     
        }
        
        if replacements["{modules}"] != "":
            replacements.update({"{sources}": ""})

        lines = []
        with open(self.sonar_template) as infile:
            for line in infile:
                for src, target in replacements.items():
                    line = line.replace(src, target)
                lines.append(line)

        with open(self.sonar_folder + "{}.sonarsource.properties".format(system), 'w') as outfile:
            for line in lines:
                outfile.write(line)

        utils.ok_text("Arquivo {}.sonarsource.properties criado com sucesso.".format(system))

    def commit_analyzer(self):
        """ Main function to analyze commit. """

        utils.verify_branch_is_merging(self.git_command)

        if self.scan_status:
            utils.print_("\n")
            utils.print_(" ANALISE DE CODIGO PELO SONARQUBE INICIADO")
            utils.print_("=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=-=\n")

            start_time = time.time()

            self.find_modified_files()

            utils.verify_sonar_response(self.sonar_server)

            for system in self.systems:
                self.preparing_sonar(system)
                self.run_sonar(system)

            utils.remove_folder("{}.scannerwork".format(self.base_repository))
            utils.print_(">> Analise de qualidade de codigo pelo SonarQube finalizada.")

            hours, rem = divmod(time.time() - start_time, 3600)
            minutes, seconds = divmod(rem, 60)
            utils.print_(">> Tempo de execucao: {:0>2}:{:0>2}:{:05.2f}\n".format(int(hours),int(minutes),seconds))            

            if self.scanner_error:
                utils.warning_text("Existem problemas criticos de qualidade, verifique o relatorio no navegador. Commit recusado.")
                utils.system_exit_block_commit()
            else:
                utils.ok_text("Nenhum problema encontrado. Commit liberado.")
                utils.system_exit_ok()
        else:
            utils.warning_text(">> Analise de qualidade de codigo pelo SonarQube esta desativada. Commit liberado.")
            utils.system_exit_ok()
