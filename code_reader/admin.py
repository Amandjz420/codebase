from django.contrib import admin
from code_reader.models import File, Project, ChangeRequested, Plan, Step
from code_reader.utils import run_code_reader, run_file_summarizer
from code_reader.tasks import start_code_reading

@admin.action(description="code reader on project and save content to db")
def start_reading_code(modeladmin, request, queryset):
    project_obj = queryset.first()
    start_code_reading.delay(project_obj.id)


@admin.action(description="updating the summary of new code from file in db")
def updating_the_summary_in_db(modeladmin, request, queryset):
    for file in queryset:
        run_file_summarizer(file.project.id, file.path)


class FileAdmin(admin.ModelAdmin):
    list_display = ('id', 'path', 'summary', 'analysis', 'created_at')
    list_filter = ('project', 'path')
    search_fields = ('path',)
    actions = [updating_the_summary_in_db]


class ProjectAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'user', 'created_at')
    list_filter = ('user',)
    search_fields = ('repo_path', 'name')
    actions = [start_reading_code]


class ChangeRequestAdmin(admin.ModelAdmin):
    list_display = ('id', 'project__id', 'project__name', 'description', 'created_at')
    list_filter = ('project',)
    search_fields = ('project__name', 'id')

class StepInline(admin.TabularInline):
    model = Step
    extra = 1  # Number of blank inline forms to display

@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('id', 'change_request', 'created_at')  # ID always first
    list_filter = ('change_request',)  # Filter by associated ChangeRequested
    search_fields = ('change_request__id',)  # Search by ChangeRequested model ID
    inlines = [StepInline]

@admin.register(Step)
class StepAdmin(admin.ModelAdmin):
    list_display = ('id', 'plan', 'title', 'order')  # ID always first
    list_filter = ('plan',)  # Filter by associated Plan
    search_fields = ('plan__change_request__id',)  # Search by ChangeRequested model ID
    ordering = ('plan', '-order')



admin.site.register(File, FileAdmin)
admin.site.register(Project, ProjectAdmin)
admin.site.register(ChangeRequested, ChangeRequestAdmin)

