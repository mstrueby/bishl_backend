-- get TOURNAMENT data
-- -----------------------
select 
	cs.name as name,
  replace(
	replace(
	replace(
	replace(
	replace(
	replace(
	replace(
	lower(trim(cs.name)), ' ', '-')
	, 'ü', 'ue')
	, 'ö', 'oe')
	, 'ä' ,'ae')
	, 'ß', 'ss')
	, '`', '-')
	, '.', '')
   as alias,
  cs.Code as tiny_name,
  ag.Name as age_group,
  'True' as published,
  'True' as active,
  '' as external,
  '' as seasons,
  id_tblChampionship as legacy_id
from tblchampionship cs
join tblagegroup ag on cs.id_fk_AgeGroup=ag.id_tblAgeGroup
where cs.IsActive=1 and py_doc='tournament'






-- Tests:
  
[{""year"":""2023"", ""published"":""True""}]
[{"year":"2023", "published":"True"}]

db.tournaments.updateOne({tiny_name:"SL"}, { $set: { seasons: [{year: 2023, published: true }] }  })
  
db.tournaments.updateOne({tiny_name:"SL"}, { $push: { seasons: {year: 2023, published: true } }  })
db.tournaments.updateOne({tiny_name:"SL"}, { $push: { seasons: {year: 2022, published: true } }  })
  
db.tournaments.updateMany({}, { $set: { seasons: [{year: 2023, published: true }] }  })



-- get SEASONS data
-- -----------------------
select distinct
  tcs.SeasonYear as season_year,
  cs.py_code as t_tiny_name
from tblteamchampionship tcs
join tblchampionship cs on tcs.id_fk_Championship=cs.id_tblChampionship
where 1=1
and tcs.SeasonYear in (2022, 2023)
and cs.IsExtern=0
and cs.id_fk_AgeGroup>0

db.tournaments.updateOne( {tiny_name: "SL"}, { $push: { seasons: {year:2023, published:true} } } )
db.tournaments.updateOne( {tiny_name: "BAM"}, { $push: { seasons: {year:2022, published:true} } } )
db.tournaments.updateOne( {tiny_name: "BAM"}, { $push: { seasons: {year:2023, published:true} } } )
db.tournaments.updateOne( {tiny_name: "JNL"}, { $push: { seasons: {year:2023, published:true} } } )
db.tournaments.updateOne( {tiny_name: "RLO"}, { $push: { seasons: {year:2023, published:true} } } )
db.tournaments.updateOne( {tiny_name: "LL"}, { $push: { seasons: {year:2023, published:true} } } )
db.tournaments.updateOne( {tiny_name: "RLO"}, { $push: { seasons: {year:2022, published:true} } } )
db.tournaments.updateOne( {tiny_name: "LL"}, { $push: { seasons: {year:2022, published:true} } } )
db.tournaments.updateOne( {tiny_name: "JGL"}, { $push: { seasons: {year:2022, published:true} } } )
db.tournaments.updateOne( {tiny_name: "JGL"}, { $push: { seasons: {year:2023, published:true} } } )
db.tournaments.updateOne( {tiny_name: "MINI"}, { $push: { seasons: {year:2022, published:true} } } )
db.tournaments.updateOne( {tiny_name: "MINI"}, { $push: { seasons: {year:2023, published:true} } } )


-- get ROUNDS data
-- -----------------------
select distinct
  tcs.SeasonYear as season_year,
  cs.py_code as t_tiny_name,
  cs.py_round as name,
  case cs.CreateTable when 1 then 'True' else '' end as create_standings, 
  cs.CreateTableByRound,
  'True' as create_stats,
  'True' as published
from tblteamchampionship tcs
join tblchampionship cs on tcs.id_fk_Championship=cs.id_tblChampionship
where 1=1
and tcs.SeasonYear in (2022, 2023)
and cs.IsExtern=0
and cs.id_fk_AgeGroup>0
ORDER BY 1,2,3


-- get MATCHDAYS data
select
	g.SeasonYear as season_year,
  cs.py_code as t_tiny_name,
  cs.py_round as r_name,
  COALESCE(g.Round, 'ALL_GAMES') as name,
  case when cs.py_round = 'Playoffs' then 'Playoffs' else 'Round Robin' end as type,
  date(min(g.startdate)) as start_date,
  case when date(max(g.startdate)) > date(min(g.startdate)) then date(max(g.startdate)) else '' end as end_date,
  case when cs.CreateTableByRound = 1 then 'True' else '' end as create_standings,
  '' as create_stats,
  'True' as published
from tblgame as g
join tblchampionship as cs on g.id_fk_Championship=cs.id_tblChampionship
where g.SeasonYear in (2022,2023)
and cs.id_tblchampionship not in (-1, 46)
and id_fk_gamestatus in (2,4)
group by g.SeasonYear,cs.id_tblchampionship,cs.name,cs.py_code,cs.py_round,g.Round
order by g.seasonYear, cs.py_code, cs.py_round, g.round, cs.CreateTableByRound


-- fix matchdays (youth leagues)
-- mini: 45
SELECT seasonyear, id_fk_Championship, MatchDay, week, Round, StartDate,s.id_tblstadium, s.Name, s.shortname
FROM tblgame g
join tblstadium s on g.id_fk_Stadium=s.id_tblStadium
where id_fk_championship in (45)
and g.seasonyear=2022
order by seasonyear desc, startdate
--- 2023: week: 1,7,12,25
update tblgame set round='Red Devils'
  where id_fk_championship=45 and seasonyear=2023
  and week=7;
update tblgame set round='Berlin Buffalos 2'
  where id_fk_championship=45 and seasonyear=2023
  and week=25;

-- sl: 10,43,44
where id_fk_championship in (10,43,44)
SELECT g.SeasonYear, g.id_fk_Championship, g.Round, date(g.StartDate), count(*)
  from tblgame g
  where SeasonYear=2022 and id_fk_Championship in (10,43,44)
  group by g.SeasonYear, g.id_fk_Championship, g.Round, date(g.StartDate)
  order by 1,2,3,4
--- fix:
  update tblgame g
    inner join tblstadium s on g.id_fk_Stadium=s.id_tblStadium
    set g.round=s.shortname
    where id_fk_championship in (10,43,44)
    and g.seasonyear=2022
  update tblgame g
    set round = concat(round, ' 2')
    where id_fk_championship in (10,43,44)
    and g.seasonyear=2022 
    and week in (8)

-- jgl: 35,47,48
SELECT seasonyear, id_fk_Championship, MatchDay, week, Round, StartDate,s.id_tblstadium, s.Name, s.shortname
FROM tblgame g
join tblstadium s on g.id_fk_Stadium=s.id_tblStadium
where id_fk_championship in (35,47,48)
and g.seasonyear=2023
and id_fk_gamestatus in (2,4)
order by seasonyear desc, startdate;

SELECT g.SeasonYear, g.id_fk_Championship, g.Round, date(g.StartDate), count(*)
  from tblgame g
  where SeasonYear=2022 and id_fk_Championship in (35,47,48)
  and id_fk_gamestatus in (2,4)
  group by g.SeasonYear, g.id_fk_Championship, g.Round, date(g.StartDate)
  order by 1,2,3,4
--- fix:
  update tblgame g
    inner join tblstadium s on g.id_fk_Stadium=s.id_tblStadium
    set g.round=s.shortname
    where id_fk_championship in (35,47,48)
    and g.seasonyear=2023
  update tblgame g
    set round = concat(round, ' 2')
    where id_fk_championship in (35,47,48)
    and g.seasonyear=2022 
    and week in (11,13,17)

-- jnl: 26
SELECT seasonyear, id_fk_Championship, MatchDay, week, Round, StartDate,s.id_tblstadium, s.Name, s.shortname
FROM tblgame g
join tblstadium s on g.id_fk_Stadium=s.id_tblStadium
where id_fk_championship in (26)
and g.seasonyear=2023
and id_fk_gamestatus in (2,4)
order by seasonyear desc, startdate;
-- fix:
  update tblgame g
    inner join tblstadium s on g.id_fk_Stadium=s.id_tblStadium
    set g.round=s.shortname
    where id_fk_championship in (26)
    and g.seasonyear=2023
  
  -- data preparation
SELECT * FROM `tblchampionship` where name like '%Playoffs%'
update  `tblchampionship` set py_round='Playoffs' where name like '%Playoffs%'

SELECT * FROM `tblchampionship` where name like '%Meisterrunde%'
update  `tblchampionship` set py_round='Meisterrunde' where name like '%Meisterrunde%'

SELECT * FROM `tblchampionship` where name like '%Platz%'
update  `tblchampionship` set py_round='Platzierungsrunde' where name like '%Platz%'


update `tblchampionship` set py_round = MenuText
update `tblchampionship` set py_round = null where isextern=1
  
SELECT * FROM `tblchampionship`
where 1=1
and not (
    py_round in ('Playoffs', 'Meisterrunde', 'Platzierungsrunde', 'Qualifikationsrunde', 'Hauptrunde')
	or 
    py_round like 'Gruppe%' or py_round like 'Staffel%'
    )
-- and py_round NOT in ('Playoffs', 'Meisterrunde', 'Platzierungsrunde', 'Qualifikationsrunde')  
and IsExtern=0
ORDER BY `tblchampionship`.`py_round` ASC

update `tblchampionship`
set py_round = 'Hauptrunde'
where 1=1
and not (
    py_round in ('Playoffs', 'Meisterrunde', 'Platzierungsrunde', 'Qualifikationsrunde', 'Hauptrunde')
	or 
    py_round like 'Gruppe%' or py_round like 'Staffel%'
    )
-- and py_round NOT in ('Playoffs', 'Meisterrunde', 'Platzierungsrunde', 'Qualifikationsrunde')  
and IsExtern=0


db.tournaments.updateOne({tiny_name:"RLO"}, {$push: {"seasons.$[seasons].rounds": {name:"HAUPT"}}}, { arrayFilters: [{"seasons.year": 2022}]})


db.tournaments.updateOne({tiny_name:"RLO"}, {$set: {"seasons.$[y].test": "test4"}}, {arrayFilters: [ {"y.year": 2023} ]} )
db.tournaments.updateOne({tiny_name:"RLO"}, {$set: {"seasons.$[y].rounds.$[r].test": "test4"}}, {arrayFilters: [ {"y.year": 2023}, {"r.name": "Hauptrunde"} ]} )