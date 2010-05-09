
from django import forms

from esp.cal.models import Event
from esp.resources.models import ResourceType, Resource
from esp.program.models import ProgramCheckItem

""" Forms for the new class management module.  Can be used elsewhere. """

#   Does anyone have a better idea for handling prefixes then copying the code into the __init__
#   functions?

class ManagementForm(forms.Form):
    """ A form that automatically asks the program module to populate its field
    data and choices. """
    def __init__(self, module=None, *args, **kwargs):
        super(ManagementForm, self).__init__(*args, **kwargs)
        if module:
            self.module = module
            for key in self.fields:
                if key in module.form_choice_types and isinstance(self.fields[key], forms.ChoiceField):
                    self.fields[key].choices = module.getFormChoices(key)

class ClassManageForm(ManagementForm):
    """ Class subject admin form.  When the status of a class is changed, any negative changes are
    propagated to all of the class's sections. """

    clsid = forms.IntegerField(initial=-1, widget=forms.HiddenInput)
    status = forms.ChoiceField(choices=())
    reg_status = forms.ChoiceField(required=False, choices=())
    min_grade = forms.ChoiceField(choices=())
    max_grade = forms.ChoiceField(choices=())
    class_size = forms.IntegerField(label='Max. number of students')
    progress = forms.MultipleChoiceField(required=False, label='Checklist', widget=forms.CheckboxSelectMultiple, choices=())
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={'cols': 60, 'rows': 8}))

    def __init__(self, *args, **kwargs):
        #   Handle the possibility of this keyword argument; not sure what to do with it yet.
        if 'subject' in kwargs:
            self.cls = kwargs.pop('subject')
            prefix = ''
            if 'prefix' in kwargs:
                prefix = kwargs['prefix'] + '-'
            initial_dict = self.load_data(self.cls, prefix)
            super(ClassManageForm, self).__init__(data=initial_dict, *args, **kwargs)
        else:
            super(ClassManageForm, self).__init__(*args, **kwargs)

    def load_data(self, cls, prefix=''):
        self.initial = {prefix+'status': cls.status,
            prefix+'reg_status': None,
            prefix+'min_grade': cls.grade_min, 
            prefix+'max_grade': cls.grade_max,
            prefix+'notes': cls.directors_notes,
            prefix+'class_size': cls.class_size_max,
            prefix+'clsid': cls.id,
            prefix+'progress': [cm.id for cm in cls.checklist_progress.all()]}
        return self.initial
         
    def save_data(self, cls):
        cls.status = self.cleaned_data['status']
        #   If the section's status has not already been marked, apply the subject's status.
        for sec in cls.sections.all():
            if sec.status == 0:
                sec.status = self.cleaned_data['status']
            if self.cleaned_data['reg_status']:
                sec.registration_status = self.cleaned_data['reg_status']
            #   Give the section a new capacity if the size of the class has been changed on the form.
            if self.cleaned_data['class_size'] != cls.class_size_max:
                sec.max_class_capacity = self.cleaned_data['class_size']
            sec.save()
        cls.grade_min = self.cleaned_data['min_grade']
        cls.grade_max = self.cleaned_data['max_grade']
        cls.class_size_max = self.cleaned_data['class_size']
        cls.directors_notes = self.cleaned_data['notes']
        cls.checklist_progress.clear()

        if cls.duration:
            from decimal import Decimal
            cls.duration = Decimal(str(cls.duration))
        for ci in self.cleaned_data['progress']:
            cpl = ProgramCheckItem.objects.get(id=ci)
            cls.checklist_progress.add(cpl)
        cls.save()

class SectionManageForm(ManagementForm):
    """ Class section admin form.  This allows each section to be assigned a different time and room.
    """

    secid = forms.IntegerField(initial=-1, widget=forms.HiddenInput)
    times = forms.MultipleChoiceField(required=False, choices=())
    room = forms.MultipleChoiceField(required=False, choices=())
    resources = forms.MultipleChoiceField(label='Floating Resources', required=False, choices=())
    status = forms.ChoiceField(choices=())
    class_size = forms.IntegerField(label='Max. number of students')
    reg_status = forms.ChoiceField(required=False, choices=())
    progress = forms.MultipleChoiceField(required=False, label='Checklist', widget=forms.CheckboxSelectMultiple, choices=())

    def __init__(self, *args, **kwargs):
        if 'section' in kwargs:
            self.sec = kwargs.pop('section')
            self.index = self.sec.index()
            prefix = ''
            if 'prefix' in kwargs:
                prefix = kwargs['prefix'] + '-'
            initial_dict = self.load_data(self.sec, prefix)
            super(SectionManageForm, self).__init__(data=initial_dict, *args, **kwargs)
        else:
            super(SectionManageForm, self).__init__(*args, **kwargs)

    def load_data(self, sec, prefix=''):
        self.initial = {prefix+'status': sec.status,
            prefix+'reg_status': sec.registration_status,
            prefix+'progress': [cm.id for cm in sec.checklist_progress.all()],
            prefix+'secid': sec.id,
            prefix+'class_size': sec.capacity,
            prefix+'times': [ts.id for ts in sec.meeting_times.all()]}
        ir = sec.initial_rooms()
        self.initial[prefix+'room'] = [r.name for r in ir]
        self.initial[prefix+'resources'] = [r.resource.name for r in sec.resourceassignments()]
        return self.initial

    def save_data(self, sec):
        sec.status = self.cleaned_data['status']
        if self.cleaned_data['reg_status']:
            sec.registration_status = self.cleaned_data['reg_status']
        sec.meeting_times.clear()
        for mi in self.cleaned_data['times']:
            ts = Event.objects.get(id=mi)
            ct = ResourceType.get_or_create('Classroom')
            sec.meeting_times.add(ts)
            cr = Resource.objects.filter(res_type__id=ct.id, event__id=ts.id, name__in=self.cleaned_data['room'])
            for c in cr:
                c.assign_to_section(sec, override=True)
        rooms = Resource.objects.filter(name__in=self.cleaned_data['room'])
        if rooms.count() > 0:
            sec.classroomassignments().delete()
            for r in rooms:
                sec.assign_room(r)
        sec.checklist_progress.clear()
        for ci in self.cleaned_data['progress']:
            cpl = ProgramCheckItem.objects.get(id=ci)
            sec.checklist_progress.add(cpl)
        for r in self.cleaned_data['resources']:
            for ts in sec.meeting_times.all():
                sec.parent_program.getFloatingResources(timeslot=ts, queryset=True).filter(name=r)[0].assign_to_section(sec)
        sec.max_class_capacity = self.cleaned_data['class_size']
        sec.save()
