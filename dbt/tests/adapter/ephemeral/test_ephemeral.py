import os
import re

import pytest

from dbt.tests.util import check_relations_equal, run_dbt


models__dependent_sql = """

-- multiple ephemeral refs should share a cte
select * from {{ref('base')}} where gender = 'Male'
union all
select * from {{ref('base')}} where gender = 'Female'

"""

models__double_dependent_sql = """

-- base_copy just pulls from base. Make sure the listed
-- graph of CTEs all share the same dbt_cte__base cte
select * from {{ref('base')}} where gender = 'Male'
union all
select * from {{ref('base_copy')}} where gender = 'Female'

"""

models__super_dependent_sql = """
select * from {{ref('female_only')}}
union all
select * from {{ref('double_dependent')}} where gender = 'Male'

"""

models__base__female_only_sql = """
{{ config(materialized='ephemeral') }}

select * from {{ ref('base_copy') }} where gender = 'Female'

"""

models__base__base_sql = """
{{ config(materialized='ephemeral') }}

select * from {{ this.schema }}.seed

"""

models__base__base_copy_sql = """
{{ config(materialized='ephemeral') }}

select * from {{ ref('base') }}

"""

ephemeral_errors__dependent_sql = """
-- base copy is an error
select * from {{ref('base_copy')}} where gender = 'Male'

"""

ephemeral_errors__base__base_sql = """
{{ config(materialized='ephemeral') }}

select * from {{ this.schema }}.seed

"""

ephemeral_errors__base__base_copy_sql = """
{{ config(materialized='ephemeral') }}

{{ adapter.invalid_method() }}

select * from {{ ref('base') }}

"""

models_n__ephemeral_level_two_sql = """
{{
  config(
    materialized = "ephemeral",
  )
}}
select * from {{ ref('source_table') }}

"""

models_n__root_view_sql = """
select * from {{ref("ephemeral")}}

"""

models_n__ephemeral_sql = """
{{
  config(
    materialized = "ephemeral",
  )
}}
select * from {{ref("ephemeral_level_two")}}

"""

models_n__source_table_sql = """
{{ config(materialized='table') }}

with source_data as (

    select 1 as id
    union all
    select null as id

)

select *
from source_data

"""

seeds__seed_csv = """id,first_name,last_name,email,gender,ip_address
1,Jack,Hunter,jhunter0@pbs.org,Male,59.80.20.168
2,Kathryn,Walker,kwalker1@ezinearticles.com,Female,194.121.179.35
3,Gerald,Ryan,gryan2@com.com,Male,11.3.212.243
4,Bonnie,Spencer,bspencer3@ameblo.jp,Female,216.32.196.175
5,Harold,Taylor,htaylor4@people.com.cn,Male,253.10.246.136
6,Jacqueline,Griffin,jgriffin5@t.co,Female,16.13.192.220
7,Wanda,Arnold,warnold6@google.nl,Female,232.116.150.64
8,Craig,Ortiz,cortiz7@sciencedaily.com,Male,199.126.106.13
9,Gary,Day,gday8@nih.gov,Male,35.81.68.186
10,Rose,Wright,rwright9@yahoo.co.jp,Female,236.82.178.100
11,Raymond,Kelley,rkelleya@fc2.com,Male,213.65.166.67
12,Gerald,Robinson,grobinsonb@disqus.com,Male,72.232.194.193
13,Mildred,Martinez,mmartinezc@samsung.com,Female,198.29.112.5
14,Dennis,Arnold,darnoldd@google.com,Male,86.96.3.250
15,Judy,Gray,jgraye@opensource.org,Female,79.218.162.245
16,Theresa,Garza,tgarzaf@epa.gov,Female,21.59.100.54
17,Gerald,Robertson,grobertsong@csmonitor.com,Male,131.134.82.96
18,Philip,Hernandez,phernandezh@adobe.com,Male,254.196.137.72
19,Julia,Gonzalez,jgonzalezi@cam.ac.uk,Female,84.240.227.174
20,Andrew,Davis,adavisj@patch.com,Male,9.255.67.25
21,Kimberly,Harper,kharperk@foxnews.com,Female,198.208.120.253
22,Mark,Martin,mmartinl@marketwatch.com,Male,233.138.182.153
23,Cynthia,Ruiz,cruizm@google.fr,Female,18.178.187.201
24,Samuel,Carroll,scarrolln@youtu.be,Male,128.113.96.122
25,Jennifer,Larson,jlarsono@vinaora.com,Female,98.234.85.95
26,Ashley,Perry,aperryp@rakuten.co.jp,Female,247.173.114.52
27,Howard,Rodriguez,hrodriguezq@shutterfly.com,Male,231.188.95.26
28,Amy,Brooks,abrooksr@theatlantic.com,Female,141.199.174.118
29,Louise,Warren,lwarrens@adobe.com,Female,96.105.158.28
30,Tina,Watson,twatsont@myspace.com,Female,251.142.118.177
31,Janice,Kelley,jkelleyu@creativecommons.org,Female,239.167.34.233
32,Terry,Mccoy,tmccoyv@bravesites.com,Male,117.201.183.203
33,Jeffrey,Morgan,jmorganw@surveymonkey.com,Male,78.101.78.149
34,Louis,Harvey,lharveyx@sina.com.cn,Male,51.50.0.167
35,Philip,Miller,pmillery@samsung.com,Male,103.255.222.110
36,Willie,Marshall,wmarshallz@ow.ly,Male,149.219.91.68
37,Patrick,Lopez,plopez10@redcross.org,Male,250.136.229.89
38,Adam,Jenkins,ajenkins11@harvard.edu,Male,7.36.112.81
39,Benjamin,Cruz,bcruz12@linkedin.com,Male,32.38.98.15
40,Ruby,Hawkins,rhawkins13@gmpg.org,Female,135.171.129.255
41,Carlos,Barnes,cbarnes14@a8.net,Male,240.197.85.140
42,Ruby,Griffin,rgriffin15@bravesites.com,Female,19.29.135.24
43,Sean,Mason,smason16@icq.com,Male,159.219.155.249
44,Anthony,Payne,apayne17@utexas.edu,Male,235.168.199.218
45,Steve,Cruz,scruz18@pcworld.com,Male,238.201.81.198
46,Anthony,Garcia,agarcia19@flavors.me,Male,25.85.10.18
47,Doris,Lopez,dlopez1a@sphinn.com,Female,245.218.51.238
48,Susan,Nichols,snichols1b@freewebs.com,Female,199.99.9.61
49,Wanda,Ferguson,wferguson1c@yahoo.co.jp,Female,236.241.135.21
50,Andrea,Pierce,apierce1d@google.co.uk,Female,132.40.10.209
51,Lawrence,Phillips,lphillips1e@jugem.jp,Male,72.226.82.87
52,Judy,Gilbert,jgilbert1f@multiply.com,Female,196.250.15.142
53,Eric,Williams,ewilliams1g@joomla.org,Male,222.202.73.126
54,Ralph,Romero,rromero1h@sogou.com,Male,123.184.125.212
55,Jean,Wilson,jwilson1i@ocn.ne.jp,Female,176.106.32.194
56,Lori,Reynolds,lreynolds1j@illinois.edu,Female,114.181.203.22
57,Donald,Moreno,dmoreno1k@bbc.co.uk,Male,233.249.97.60
58,Steven,Berry,sberry1l@eepurl.com,Male,186.193.50.50
59,Theresa,Shaw,tshaw1m@people.com.cn,Female,120.37.71.222
60,John,Stephens,jstephens1n@nationalgeographic.com,Male,191.87.127.115
61,Richard,Jacobs,rjacobs1o@state.tx.us,Male,66.210.83.155
62,Andrew,Lawson,alawson1p@over-blog.com,Male,54.98.36.94
63,Peter,Morgan,pmorgan1q@rambler.ru,Male,14.77.29.106
64,Nicole,Garrett,ngarrett1r@zimbio.com,Female,21.127.74.68
65,Joshua,Kim,jkim1s@edublogs.org,Male,57.255.207.41
66,Ralph,Roberts,rroberts1t@people.com.cn,Male,222.143.131.109
67,George,Montgomery,gmontgomery1u@smugmug.com,Male,76.75.111.77
68,Gerald,Alvarez,galvarez1v@flavors.me,Male,58.157.186.194
69,Donald,Olson,dolson1w@whitehouse.gov,Male,69.65.74.135
70,Carlos,Morgan,cmorgan1x@pbs.org,Male,96.20.140.87
71,Aaron,Stanley,astanley1y@webnode.com,Male,163.119.217.44
72,Virginia,Long,vlong1z@spiegel.de,Female,204.150.194.182
73,Robert,Berry,rberry20@tripadvisor.com,Male,104.19.48.241
74,Antonio,Brooks,abrooks21@unesco.org,Male,210.31.7.24
75,Ruby,Garcia,rgarcia22@ovh.net,Female,233.218.162.214
76,Jack,Hanson,jhanson23@blogtalkradio.com,Male,31.55.46.199
77,Kathryn,Nelson,knelson24@walmart.com,Female,14.189.146.41
78,Jason,Reed,jreed25@printfriendly.com,Male,141.189.89.255
79,George,Coleman,gcoleman26@people.com.cn,Male,81.189.221.144
80,Rose,King,rking27@ucoz.com,Female,212.123.168.231
81,Johnny,Holmes,jholmes28@boston.com,Male,177.3.93.188
82,Katherine,Gilbert,kgilbert29@altervista.org,Female,199.215.169.61
83,Joshua,Thomas,jthomas2a@ustream.tv,Male,0.8.205.30
84,Julie,Perry,jperry2b@opensource.org,Female,60.116.114.192
85,Richard,Perry,rperry2c@oracle.com,Male,181.125.70.232
86,Kenneth,Ruiz,kruiz2d@wikimedia.org,Male,189.105.137.109
87,Jose,Morgan,jmorgan2e@webnode.com,Male,101.134.215.156
88,Donald,Campbell,dcampbell2f@goo.ne.jp,Male,102.120.215.84
89,Debra,Collins,dcollins2g@uol.com.br,Female,90.13.153.235
90,Jesse,Johnson,jjohnson2h@stumbleupon.com,Male,225.178.125.53
91,Elizabeth,Stone,estone2i@histats.com,Female,123.184.126.221
92,Angela,Rogers,arogers2j@goodreads.com,Female,98.104.132.187
93,Emily,Dixon,edixon2k@mlb.com,Female,39.190.75.57
94,Albert,Scott,ascott2l@tinypic.com,Male,40.209.13.189
95,Barbara,Peterson,bpeterson2m@ow.ly,Female,75.249.136.180
96,Adam,Greene,agreene2n@fastcompany.com,Male,184.173.109.144
97,Earl,Sanders,esanders2o@hc360.com,Male,247.34.90.117
98,Angela,Brooks,abrooks2p@mtv.com,Female,10.63.249.126
99,Harold,Foster,hfoster2q@privacy.gov.au,Male,139.214.40.244
100,Carl,Meyer,cmeyer2r@disqus.com,Male,204.117.7.88
"""


class BaseEphemeral:
    @pytest.fixture(scope="class")
    def seeds(self):
        return {
            "seed.csv": seeds__seed_csv,
        }


class BaseEphemeralMulti:
    @pytest.fixture(scope="class")
    def seeds(self):
        return {
            "seed.csv": seeds__seed_csv,
        }

    @pytest.fixture(scope="class")
    def models(self):
        return {
            "dependent.sql": models__dependent_sql,
            "double_dependent.sql": models__double_dependent_sql,
            "super_dependent.sql": models__super_dependent_sql,
            "base": {
                "female_only.sql": models__base__female_only_sql,
                "base.sql": models__base__base_sql,
                "base_copy.sql": models__base__base_copy_sql,
            },
        }


class TestEphemeralMulti(BaseEphemeralMulti):
    def test_ephemeral_multi(self, project):
        run_dbt(["seed"])
        results = run_dbt(["run"])
        assert len(results) == 3

        check_relations_equal(project.adapter, ["seed", "dependent"])
        check_relations_equal(project.adapter, ["seed", "double_dependent"])
        check_relations_equal(project.adapter, ["seed", "super_dependent"])
        assert os.path.exists("./target/run/test/models/double_dependent.sql")
        with open("./target/run/test/models/double_dependent.sql", "r") as fp:
            sql_file = fp.read()

        sql_file = re.sub(r"\d+", "", sql_file)
        expected_sql = (
            'create view "dbt"."test_test_ephemeral"."double_dependent__dbt_tmp" as ('
            "with __dbt__cte__base as ("
            "select * from test_test_ephemeral.seed"
            "),  __dbt__cte__base_copy as ("
            "select * from __dbt__cte__base"
            ")-- base_copy just pulls from base. Make sure the listed"
            "-- graph of CTEs all share the same dbt_cte__base cte"
            "select * from __dbt__cte__base where gender = 'Male'"
            "union all"
            "select * from __dbt__cte__base_copy where gender = 'Female'"
            ");"
        )
        sql_file = "".join(sql_file.split())
        expected_sql = "".join(expected_sql.split())
        assert sql_file == expected_sql


class TestEphemeralNested(BaseEphemeral):
    @pytest.fixture(scope="class")
    def models(self):
        return {
            "ephemeral_level_two.sql": models_n__ephemeral_level_two_sql,
            "root_view.sql": models_n__root_view_sql,
            "ephemeral.sql": models_n__ephemeral_sql,
            "source_table.sql": models_n__source_table_sql,
        }

    def test_ephemeral_nested(self, project):
        results = run_dbt(["run"])
        assert len(results) == 2
        assert os.path.exists("./target/run/test/models/root_view.sql")
        with open("./target/run/test/models/root_view.sql", "r") as fp:
            sql_file = fp.read()

        sql_file = re.sub(r"\d+", "", sql_file)
        expected_sql = (
            'create view "dbt"."test_test_ephemeral"."root_view__dbt_tmp" as ('
            "with __dbt__cte__ephemeral_level_two as ("
            'select * from "dbt"."test_test_ephemeral"."source_table"'
            "),  __dbt__cte__ephemeral as ("
            "select * from __dbt__cte__ephemeral_level_two"
            ")select * from __dbt__cte__ephemeral"
            ");"
        )

        sql_file = "".join(sql_file.split())
        expected_sql = "".join(expected_sql.split())
        assert sql_file == expected_sql


class TestEphemeralErrorHandling(BaseEphemeral):
    @pytest.fixture(scope="class")
    def models(self):
        return {
            "dependent.sql": ephemeral_errors__dependent_sql,
            "base": {
                "base.sql": ephemeral_errors__base__base_sql,
                "base_copy.sql": ephemeral_errors__base__base_copy_sql,
            },
        }

    def test_ephemeral_error_handling(self, project):
        results = run_dbt(["run"], expect_pass=False)
        assert len(results) == 1
        assert results[0].status == "skipped"
        assert "Compilation Error" in results[0].message
