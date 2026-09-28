from dataclasses import dataclass
from itertools import count


@dataclass
class Project:
    id: int
    name: str
    archived: bool = False


class Board:
    def __init__(self):
        self._projects = {}
        self._ids = count(1)

    def create_project(self, name):
        project = Project(next(self._ids), name)
        self._projects[project.id] = project
        return project

    def rename_project(self, project_id, name):
        self._projects[project_id].name = name

    def archive_project(self, project_id):
        self._projects[project_id].archived = True

    def dashboard(self):
        return [project.name for project in self._projects.values() if not project.archived]
