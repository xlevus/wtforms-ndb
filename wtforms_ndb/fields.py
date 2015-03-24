from __future__ import unicode_literals
import logging

import decimal
import operator
import warnings

from wtforms import fields, widgets
from wtforms.compat import text_type, string_types


class KeyPropertyField(fields.SelectFieldBase):
    """
    A field for ``ndb.KeyProperty``. The list items are rendered in a select.

    :param reference_class:
        A db.Model class which will be used to generate the default query
        to make the list of items. If this is not specified, The `query`
        property must be overridden before validation.
    :param get_label:
        If a string, use this attribute on the model class as the label
        associated with each option. If a one-argument callable, this callable
        will be passed model instance and expected to return the label text.
        Otherwise, the model object's `__str__` or `__unicode__` will be used.
    :param allow_blank:
        If set to true, a blank choice will be added to the top of the list
        to allow `None` to be chosen.
    :param blank_text:
        Use this to override the default blank option's label.
    """
    widget = widgets.Select()

    def __init__(self, label=None, validators=None, reference_class=None,
                 get_label=None, allow_blank=False, blank_text='', query=None,
                 **kwargs):
        super(KeyPropertyField, self).__init__(label, validators, **kwargs)
        if get_label is None:
            self.get_label = lambda x: x
        elif isinstance(get_label, basestring):
            self.get_label = operator.attrgetter(get_label)
        else:
            self.get_label = get_label

        self.allow_blank = allow_blank
        self.blank_text = blank_text
        self._set_data(None)

        if reference_class is not None:
            self.query = query or reference_class.query()

    def _get_data(self):
        if self._formdata is not None:
            for obj in self.query:
                if obj.key.urlsafe() == self._formdata:
                    self._set_data(obj)
                    break
        return self._data

    def _set_data(self, data):
        self._data = data
        self._formdata = None

    data = property(_get_data, _set_data)

    def iter_choices(self):
        if self.allow_blank:
            yield ('__None', self.blank_text, self.data is None)

        for obj in self.query:
            key = obj.key.urlsafe()
            label = self.get_label(obj)
            yield (key, label, (self.data.key == obj.key) if self.data else False)

    def process_data(self, data):
        if data:
            self.data = data.get()

    def process_formdata(self, valuelist):
        if valuelist:
            if valuelist[0] == '__None':
                self.data = None
            else:
                self._data = None
                self._formdata = valuelist[0]

    def pre_validate(self, form):
        if self.data is not None:
            for obj in self.query:
                if self.data.key == obj.key:
                    break
            else:
                raise ValueError(self.gettext('Not a valid choice'))
        elif not self.allow_blank:
            raise ValueError(self.gettext('Not a valid choice'))

    def populate_obj(self, obj, name):
        if self.data:
            setattr(obj, name, self.data.key)
        else:
            setattr(obj, name, None)


class SelectMultipleMixin(object):
    widget = widgets.Select(multiple=True)

    def iter_choices(self):
        if self.data:
            data_keys = [obj.key for obj in self.data if obj is not None]
        else:
            data_keys = []

        for obj  in self.query:
            key = obj.key.urlsafe()
            label = self.get_label(obj)
            selected = obj.key in data_keys
            logging.debug("%r", obj)
            yield (key, label, selected)

    def process_data(self, value):
        if value:
            futures = [x.get_async() for x in value]
            self.data = [x.get_result() for x in futures]
        else:
            self.data = None

    def process_formdata(self, valuelist):
        self._formdata = valuelist

    def pre_validate(self, form):
        if self.data:
            values = list(self.query)
            for d in self.data:
                if d not in values:
                    raise ValueError("%(value)s is not a valid choice for this field")

    def _get_data(self):
        if self._formdata is not None:
            m = {obj.key.urlsafe(): obj for obj in self.query}
            self._set_data([m.get(x, x) for x in self._formdata])
        return self._data

    def _set_data(self, data):
        self._data = data
        self._formdata = None

    data = property(_get_data, _set_data)

    def populate_obj(self, obj, name):
        if self.data:
            setattr(obj, name, [x.key for x in self.data if x is not None])
        else:
            setattr(obj, name, [])


class RepeatedKeyPropertyField(SelectMultipleMixin, KeyPropertyField):
    widget = widgets.Select(multiple=True)


class PrefetchedKeyPropertyField(KeyPropertyField):
    """
    A field for ``ndb.KeyProperty``. The list items are rendered in a select.
    The query is executed asynchronously. This should provide noticable speed
    improvements on forms with multiple KeyProperty fields.

    :param reference_class:
        A db.Model class which will be used to generate the default query
        to make the list of items. If this is not provided, a ``query``
        argument must be passed in
    :param query:
        A NDB query to call against.
    :param get_label:
        If a string, use this attribute on the model class as the label
        associated with each option. If a one-argument callable, this callable
        will be passed model instance and expected to return the label text.
        Otherwise, the model object's `__str__` or `__unicode__` will be used.
    :param allow_blank:
        If set to true, a blank choice will be added to the top of the list
        to allow `None` to be chosen.
    :param blank_text:
        Use this to override the default blank option's label.
    """
    widget = widgets.Select()

    def __init__(self, label=None, validators=None, reference_class=None,
                 query=None, get_label=None, allow_blank=False, blank_text='',
                 **kwargs):
        super(KeyPropertyField, self).__init__(label, validators, **kwargs)
        if get_label is None:
            self.get_label = lambda x: x
        elif isinstance(get_label, basestring):
            self.get_label = operator.attrgetter(get_label)
        else:
            self.get_label = get_label

        self.allow_blank = allow_blank
        self.blank_text = blank_text
        self._set_data(None)

        if reference_class is not None and not query:
            query = reference_class.query()

        self._query = query.fetch_async()

    @property
    def query(self):
        return self._query.get_result()


class RepeatedPrefetchedKeyPropertyField(SelectMultipleMixin, PrefetchedKeyPropertyField):
    widget = widgets.Select(multiple=True)


class StringListPropertyField(fields.TextAreaField):
    """
    A field for ``db.StringListProperty``. The list items are rendered in a
    textarea.
    """
    def _value(self):
        if self.raw_data:
            return self.raw_data[0]
        else:
            return self.data and text_type("\n".join(self.data)) or ''

    def process_formdata(self, valuelist):
        if valuelist:
            try:
                self.data = valuelist[0].splitlines()
            except ValueError:
                raise ValueError(self.gettext('Not a valid list'))


class IntegerListPropertyField(fields.TextAreaField):
    """
    A field for ``db.StringListProperty``. The list items are rendered in a
    textarea.
    """
    def _value(self):
        if self.raw_data:
            return self.raw_data[0]
        else:
            return text_type('\n'.join(self.data)) if self.data else ''

    def process_formdata(self, valuelist):
        if valuelist:
            try:
                self.data = [int(value) for value in valuelist[0].splitlines()]
            except ValueError:
                raise ValueError(self.gettext('Not a valid integer list'))


class GeoPtPropertyField(fields.TextField):

    def process_formdata(self, valuelist):
        if valuelist:
            try:
                lat, lon = valuelist[0].split(',')
                self.data = '%s,%s' % (decimal.Decimal(lat.strip()), decimal.Decimal(lon.strip()),)
            except (decimal.InvalidOperation, ValueError):
                raise ValueError('Not a valid coordinate location')
