-- get TOURNAMENT data
-- -----------------------
select 
  cs.name as name,
  py_t_alias as alias,
  cs.Code as tinyName,
  -- json_object("key", ag.py_key, "value", ag.py_value) as ageGroup,
  py_ageGroup as ageGroup,
  'True' as published,
  'True' as active,
  -- '' as external,
  /*
  json_object(
    'numOfPeriods', cs.NumOfPeriods,
    'periodLengthMin', cs.PeriodLength,
    'pointsWinReg', cs.PointsWinReg,
    'pointsLossReg', cs.PointsLossReg,
    'pointsDrawReg', cs.PointsTie,
    'overtime', case when cs.IsOvertime = 1 then 'True' else 'False' end,
    'numOfPeriodsOvertime', cs.NumOfPeriodsOT,
    'periodLengthMinOvertime', cs.PeriodLengthOT,
    'pointsWinOvertime', cs.PointsWinOT,
    'pointsLossOvertime', cs.PointsLossOT,
    'shootout', case when cs.IsShootout = 1 then 'True' else 'False' end,
    'pointsWinShootout', cs.PointsWinSO,
    'pointsLossShootout', cs.PointsLossSO
  ) as defaultSettings,
  */
  json_object(
    'pointsWinReg', cs.PointsWinReg,
    'pointsLossReg', cs.PointsLossReg,
    'pointsDrawReg', cs.PointsTie,
    'pointsWinOvertime', cs.PointsWinOT,
    'pointsLossOvertime', cs.PointsLossOT,
    'pointsWinShootout', cs.PointsWinSO,
    'pointsLossShootout', cs.PointsLossSO
  ) as standingsSettings,
  -- '' as seasons,
  id_tblChampionship as legacyId
from tblchampionship cs
join tblagegroup ag on cs.id_fk_AgeGroup=ag.id_tblAgeGroup
where 1=1
  -- and cs.IsActive=1 
  and py_doc='tournament'
  and cs.id_tblChampionship in (45,14,10,51,35,26,28,27)


-- fixes
  update tblchampionship 
  set py_t_alias=
    replace(
      replace(
        replace(
          replace(  
            replace(
              replace(
                replace(lower(trim(Name)), ' ', '-')
                , 'ü', 'ue')
            , 'ö', 'oe')
          , 'ä' ,'ae')
        , 'ß', 'ss')
      , '`', '-')
    , '.', '')
  where py_doc='tournament'

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
    tcs.SeasonYear as name,
    replace(
      replace(
        replace(
          replace(  
            replace(
              replace(
                replace(lower(trim(tcs.SeasonYear)), ' ', '-')
              , 'ü', 'ue')
            , 'ö', 'oe')
          , 'ä' ,'ae')
        , 'ß', 'ss')
      , '`', '-')
    , '.', '') as alias,
    cs.py_t_alias as t_alias
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
      cs.py_t_alias as t_alias,
      tcs.SeasonYear as s_alias,
      cs.py_round as name,
      cs.py_round_alias as alias,
      case cs.CreateTable when 1 then 'True' else 'False' end as createStandings, 
      case cs.PlayerStatSortOrder when 'value' then 'True' else 'False' end as createStats,
      py_matchdaysType as matchdaysType, -- Spieltag, Turnier, Runde, Gruppe
      py_matchdaysSortedBy as matchdaysSortedBy, -- Startdatum, Name
      -- min(date(g.StartDate)) as startDate,
      -- max(date(g.StartDate)) as endDate,
      min(g.StartDate) as startDate,
      max(g.StartDate) as endDate,
      json_object(
        'numOfPeriods', cs.NumOfPeriods,
        'periodLengthMin', cs.PeriodLength,
        'overtime', case when cs.IsOvertime = 1 then 'True' else 'False' end,
        'numOfPeriodsOvertime', cs.NumOfPeriodsOT,
        'periodLengthMinOvertime', cs.PeriodLengthOT,
        'shootout', case when cs.IsShootout = 1 then 'True' else 'False' end
      ) as matchSettings,
      'True' as published,
      cs.CreateTableByRound
    from tblteamchampionship tcs
    join tblchampionship cs on tcs.id_fk_Championship=cs.id_tblChampionship
    join tblgame g on tcs.SeasonYear=g.SeasonYear and cs.id_tblChampionship=g.id_fk_Championship
    where 1=1
    and tcs.SeasonYear in (2022, 2023)
    and cs.IsExtern=0
    and cs.id_fk_AgeGroup>0
    group by tcs.SeasonYear, cs.py_code, cs.py_round, cs.CreateTable, cs.CreateTableByRound  
  ORDER BY 1,2,3


-- get MATCHDAYS data
select
	g.SeasonYear as s_alias,
  cs.py_t_alias as t_alias,
  cs.py_round_alias as r_alias,
  COALESCE(g.Round, 'ALL_GAMES') as name,
  COALESCE(g.py_md_alias, 'all_games') as alias,
  json_object(
    'key', case when cs.py_round = 'Playoffs' then 'PLAYOFFS' else 'REGULAR' end,
    'value', case when cs.py_round = 'Playoffs' then 'Playoffs' else 'Regulär' end
  ) as type,
  -- date(min(g.startdate)) as startDate,
  -- date(max(g.startdate)) as endDate,
  min(g.startdate) as startDate,
  max(g.startdate) as endDate,
  json_object(
    'numOfPeriods', cs.NumOfPeriods,
    'periodLengthMin', cs.PeriodLength,
    'overtime', case when cs.IsOvertime = 1 then 'True' else 'False' end,
    'numOfPeriodsOvertime', cs.NumOfPeriodsOT,
    'periodLengthMinOvertime', cs.PeriodLengthOT,
    'shootout', case when cs.IsShootout = 1 then 'True' else 'False' end
  ) as matchSettings,
  case cs.CreateTable when 1 then 'True' else 'False' end as createStandings, 
  case cs.PlayerStatSortOrder when 'value' then 'True' else 'False' end as createStats,
  'True' as published
from tblgame as g
join tblchampionship as cs on g.id_fk_Championship=cs.id_tblChampionship
where g.SeasonYear in (2022,2023)
and cs.id_tblchampionship not in (-1, 46)
and id_fk_gamestatus in (2,4)
group by g.SeasonYear,cs.id_tblchampionship,cs.name,cs.py_code,cs.py_round,g.Round
order by g.seasonYear, cs.py_code, cs.py_round, g.round, cs.CreateTableByRound

-- alias
  update `tblgame` 
  set py_md_alias=
    replace(
      replace(
        replace(
          replace(  
            replace(
              replace(
                replace(lower(trim(coalesce(Round, 'ALL_GAMES')), ' ', '-')
                , 'ü', 'ue')
            , 'ö', 'oe')
          , 'ä' ,'ae')
        , 'ß', 'ss')
      , '`', '-')
    , '.', '')
   where SeasonYear in (2022, 2023)

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


-- get MATCHES data
-- -----------------

-- with history (joining tblteamseason)
select
  json_object('name', cs.py_name, 'alias', cs.py_t_alias) as tournament,
  json_object('name', cast(g.SeasonYear as char(4)), 'alias', cast(g.SeasonYear as char(4))) as season,
  json_object('name', cs.py_round, 'alias', cs.py_round_alias) as round,
  json_object(
    'name', COALESCE(g.Round, 'ALL_GAMES'), 
    'alias', COALESCE(g.py_md_alias, 'all_games')
  ) as matchday,
  g.id_tblGame as matchId,
  json_object(
    'fullName', th.Name, 
    'shortName', th.ShortName,
    'tinyName', th.TinyName,
    'logo', th.py_logo,
    'stats', json_object(
      'goalsFor', st.GoalsH,
      'goalsAgainst', st.GoalsA
    )
  ) as home,
  ta.Name, ta.ShortName, ta.tinyName,
  json_object(
    'fullName', ta.Name, 
    'shortName', ta.ShortName,
    'tinyName', ta.TinyName,
    'logo', ta.py_logo,
    'stats', json_object(
      'goalsFor', st.GoalsA,
      'goalsAgainst', st.GoalsH
    )
  ) as away,
  gs.py_doc as matchStatus,
  s.Name as venue,
  case g.IsOvertime when 1 then 'True' else 'False' end as overtime,
  case g.IsShootout when 1 then 'True' else 'False' end as shootout,
  json_object(
    'key', 
    case when g.IsOvertime = 1 then 'OVERTIME' else 
      case when g.IsShootout = 1 then 'SHOOTOUT' else 'REGULAR' end    
    end,
    'value',
    case when g.IsOvertime = 1 then 'Verlängerung' else
      case when g.IsShootout = 1 then 'Penaltyschießen' else 'Regulär' end
    end
  ) as finishType,
  g.startdate as startDate,
  'True' as published
from tblgame as g
join tblchampionship as cs on g.id_fk_Championship=cs.id_tblChampionship
join tblgamestatus as gs on g.id_fk_GameStatus=gs.id_tblGameStatus
join tblstadium as s on g.id_fk_Stadium=s.id_tblStadium
join tblteamseason as th on g.id_fk_TeamHome=th.id_fk_Team and g.SeasonYear=th.SeasonYear
join tblteamseason as ta on g.id_fk_TeamAway=ta.id_fk_Team and g.SeasonYear=ta.SeasonYear
left join tblgamestats as st on g.id_tblgame = st.id_fk_game
where g.SeasonYear in (2022,2023)
and cs.id_tblchampionship not in (-1, 46)
and id_fk_gamestatus in (2,4)

-- without history (NOT joining tblteamseason)
select
  cs.py_code as t_tinyName,
  g.SeasonYear as seasonYear,
  cs.py_round as r_name,
  COALESCE(g.Round, 'ALL_GAMES') as md_name,
  g.id_tblGame as matchId,
  th.Name, th.ShortName, th.tinyName,
  json_object(
    'fullName', th.Name, 
    'shortName', th.ShortName,
    'tinyName', th.TinyName,
    'logo', th.py_logo
  ) as homeTeam,
  ta.Name, ta.ShortName, ta.tinyName,
  json_object(
    'fullName', ta.Name, 
    'shortName', ta.ShortName,
    'tinyName', ta.TinyName,
    'logo', ta.py_logo
  ) as awayTeam,
  gs.Name as status,
  s.Name as venue,
  st.GoalsH as homeScore,
  st.GoalsA as awayScore,
  g.IsOvertime as overtime,
  g.IsShootout as shootout,
  g.startdate as startTime,
  'True' as published
from tblgame as g
join tblchampionship as cs on g.id_fk_Championship=cs.id_tblChampionship
join tblgamestatus as gs on g.id_fk_GameStatus=gs.id_tblGameStatus
join tblstadium as s on g.id_fk_Stadium=s.id_tblStadium
join tblteam as th on g.id_fk_TeamHome=th.id_tblTeam
join tblteam as ta on g.id_fk_TeamAway=ta.id_tblTeam
left join tblgamestats as st on g.id_tblgame = st.id_fk_game
where g.SeasonYear in (2022,2023)
and cs.id_tblchampionship not in (-1, 46)
and id_fk_gamestatus in (2,4)

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