from django.contrib import admin
from code_reader.models import File, Project
from code_reader.utils import run_code_reader, run_file_summarizer


@admin.action(description="code reader on project and save content to db")
def start_reading_code(modeladmin, request, queryset):
    project_obj = queryset.first()
    run_code_reader(project_obj)


@admin.action(description="updating the summary of new code from file in db")
def updating_the_summary_in_db(modeladmin, request, queryset):
    for file in queryset:
        run_file_summarizer(file.project.id, file.path)


class FileAdmin(admin.ModelAdmin):
    list_display = ('path', 'summary', 'analysis')
    list_filter = ('project', 'path')
    search_fields = ('path',)
    actions = [updating_the_summary_in_db]


class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'user')
    list_filter = ('user',)
    search_fields = ('repo_path', 'name')
    actions = [start_reading_code]

admin.site.register(File, FileAdmin)
admin.site.register(Project, ProjectAdmin)
