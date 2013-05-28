# Copyright (c) 2010-2013, GEM Foundation.
#
# OpenQuake is free software: you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# OpenQuake is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with OpenQuake.  If not, see <http://www.gnu.org/licenses/>.


# vim: tabstop=4 shiftwidth=4 softtabstop=4
"""
Base classes for the output methods of the various codecs.
"""

import logging
import atexit
from cStringIO import StringIO

from django.db import transaction
from django.db import connections
from django.db import router
from django.contrib.gis.db.models.fields import GeometryField
from django.contrib.gis.geos.point import Point

LOGGER = logging.getLogger('serializer')


# pylint: disable=W0212
class BulkInserter(object):
    """Handle bulk object insertion"""

    def __init__(self, dj_model, max_cache_size=None):
        """
        Create a new bulk inserter for a Django model class

        :param dj_model:
            Django model class
        :param int max_cache_size:
            The number of entries to cache before flushing/inserting. This
            helps to limit memory consumption for large sets of inserts.

            The default value is `None`, which means there is no maximum.
        """
        self.table = dj_model
        self.max_cache_size = max_cache_size
        self.fields = None
        self.values = []
        self.count = 0

    def add_entry(self, **kwargs):
        """
        Add a new entry to be inserted

        The first time the method is called the field list is stored;
        subsequent add_entry() calls must provide the same set of
        keyword arguments.

        Handles PostGIS/GeoDjango types.
        """
        if not self.fields:
            self.fields = kwargs.keys()
        assert set(self.fields) == set(kwargs.keys())
        for k in self.fields:
            self.values.append(kwargs[k])
        self.count += 1

        # If we have hit the `max_cache_size` is set,
        if self.max_cache_size is not None:
            # check if we have hit the maximum insert the current batch.
            if len(self.values) >= self.max_cache_size:
                self.flush()

    def flush(self):
        """Inserts the entries in the database using a bulk insert query"""
        if not self.values:
            return

        alias = router.db_for_write(self.table)
        cursor = connections[alias].cursor()
        value_args = []

        field_map = dict()
        for f in self.table._meta.fields:
            field_map[f.column] = f

        for f in self.fields:
            col = field_map[f]
            if isinstance(col, GeometryField):
                value_args.append('GeomFromText(%%s, %d)' % col.srid)
            else:
                value_args.append('%s')

        sql = "INSERT INTO \"%s\" (%s) VALUES " % (
            self.table._meta.db_table, ", ".join(self.fields)) + \
            ", ".join(["(" + ", ".join(value_args) + ")"] * self.count)
        cursor.execute(sql, self.values)
        transaction.set_dirty(using=alias)

        self.fields = None
        self.values = []
        self.count = 0


class DummyMonitor(object):
    """
    This class makes it easy to disable the monitoring
    in client code. Disabling the monitor can improve the performance.
    """
    def __init__(self, operation='', job_id=0, *args, **kw):
        self.operation = operation
        self.job_id = job_id

    def __enter__(self):
        return self

    def copy(self, operation):
        return self.__class__(operation, self.job_id)

    def __exit__(self, etype, exc, tb):
        pass


# In the future this class may replace openquake.engine.writer.BulkInserter
# since it is much more efficient (even hundreds of times for bulky updates)
# being based on COPY FROM. CacheInserter objects are not thread-safe.
class CacheInserter(object):
    """
    Bulk insert bunches of Django objects by converting them in strings
    and by using COPY FROM.
    """
    instances = []

    @classmethod
    def flushall(cls):
        """
        Flush the caches of all the instances of CacheInserter.
        """
        for instance in cls.instances:
            instance.flush()

    def __init__(self, dj_model, max_cache_size):
        self.table = dj_model
        self.max_cache_size = max_cache_size
        self.alias = router.db_for_write(dj_model)
        meta = dj_model._meta
        self.tname = '"%s"' % meta.db_table
        meta._fill_fields_cache()
        self.fields = [f.attname for f in meta._field_name_cache[1:]]
        # skip the first field, the id

        self.values = []
        self.instances.append(self)

    def add(self, obj):
        """
        :param obj: a Django model object

        Append an object to the list of objects to save. If the list exceeds
        the max_cache_size, flush it on the database.
        """
        assert isinstance(obj, self.table)
        self.values.append(obj)
        if len(self.values) >= self.max_cache_size:
            self.flush()

    def flush(self, monitor=DummyMonitor()):
        """
        Save the pending objects on the database with a COPY FROM.
        """
        if not self.values:
            return

        # perform some introspection
        objects = self.values

        # generate a big string with the objects and save it with COPY FROM
        text = '\n'.join(self.to_line(obj) for obj in objects)
        with transaction.commit_on_success(using=self.alias):
            curs = connections[self.alias].cursor()
            with monitor.copy('bulk inserting into %s' % self.tname):
                curs.copy_from(StringIO(text), self.tname, columns=self.fields)

        ## TODO: should we add an assert that the number of rows stored
        ## in the db is the expected one? I (MS) have seen a case where
        ## this fails silently (it was for True/False not converted in t/f)

        LOGGER.debug('saved %d rows in %s', len(self.values), self.tname)
        self.values = []

    def to_line(self, obj):
        """
        Convert the fields of a Django object into a line string suitable
        for import via COPY FROM. The encoding is UTF8.
        """
        cols = []
        for f in self.fields:
            col = getattr(obj, f)
            if col is None:
                col = r'\N'
            elif isinstance(col, bool):
                col = 't' if col else 'f'
            elif isinstance(col, Point):
                col = 'SRID=4326;' + col.wkt
            elif isinstance(col, GeometryField):
                col = col.wkt()
            elif isinstance(col, list):  # for numeric arrays; this is fragile
                col = self.array_to_pgstring(col)
            else:
                col = unicode(col).encode('utf8')
            cols.append(col)
        return '\t'.join(cols)

    @staticmethod
    def array_to_pgstring(a):
        ls = []
        for n in a:
            s = str(n)
            if s.endswith('L'):  # strip the trailing "L"
                s = s[:-1]
            ls.append(s)
        return '{%s}' % ','.join(ls)


# just to make sure that flushall is always called
atexit.register(CacheInserter.flushall)
