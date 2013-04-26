#  -*- coding: utf-8 -*-
#  vim: tabstop=4 shiftwidth=4 softtabstop=4

#  Copyright (c) 2013, GEM Foundation

#  OpenQuake is free software: you can redistribute it and/or modify it
#  under the terms of the GNU Affero General Public License as published
#  by the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.

#  OpenQuake is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.

#  You should have received a copy of the GNU Affero General Public License
#  along with OpenQuake.  If not, see <http://www.gnu.org/licenses/>.

"""
Helpers to import test data with the PGImporter
"""

from openquake.engine.db.models import GmfCollection
from openquake.engine.tools.pg_importer import PGImporter

# id owner_id oq_job_id display_name output_type last_update
output = '''\
$out1	1	\N	gmf-rlz	gmf	2013-04-11 03:08:46.797773
'''

# id output_id lt_realization_id
gmf_collection = '''\
$coll1	$out1	\N
'''

imts = [('PGA', None, None), ('SA', 0.1, 5)]

num_tasks = 4

gmf_agg = '''\
$agg1	$coll1	PGA	\N	\N	{0.252294938306868,0.151132933300216,0.0477298423601717,0.0142826375129993,0.053177248284009,0.0346846321726566,0.00509134495333861,0.23164352054727,0.00327192823764393}	{709346,709350,709352,709354,709356,709358,709360,709348,709362}	0101000020E610000000000000000000000000000000000000
$agg2	$coll1	PGA	\N	\N	{0.00894558476907965,0.0720017584564812,0.0209473778737383,0.00810452525440645,0.014933592444171,0.0247923869973088,0.0187720473080453,0.0264362061113464,0.00257996694936015}	{709346,709350,709352,709354,709356,709358,709360,709348,709362}	0101000020E61000000000000000000000000000000000E03F
$agg3	$coll1	SA	0.1	5	{0.729799582246203,0.0571210320882165,0.0851203442596857,0.0512935367105168,0.0647094509155515,0.156892787041029,0.0168322906204596,0.73468651581123,0.0174152488960141}	{709346,709350,709352,709354,709356,709358,709360,709348,709362}	0101000020E610000000000000000000000000000000000000
$agg4	$coll1	SA	0.1	5	{0.0141248596268433,0.0457237221727419,0.0250737105548348,0.0466984811965513,0.0137011674890562,0.015367505662649,0.0267122052505091,0.130897324686063,0.00365106296335889}	{709346,709350,709352,709354,709356,709358,709360,709348,709362}	0101000020E61000000000000000000000000000000000E03F
'''


def import_a_gmf_collection(conn):
    """
    Import a fixed gmf_collection into the database. This is a useful
    helper to populate the risk tests without having to run a full hazard
    computation.

    :param conn: a database connection
    :returns: the imported GmfCollection object

    NB: conn.cursor() must return a psycopg2 cursor with a
    .copy_expert() method.
    """
    PGImporter(conn).import_all([
        ('uiapi.output', output),
        ('hzrdr.gmf_collection', gmf_collection),
        ('hzrdr.gmf_agg', gmf_agg),
    ])
    return GmfCollection.objects.latest('id')
