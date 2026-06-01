#!/usr/bin/env python3
"""
球队名称映射表 - 竞彩网中文 <-> The Odds API 英文
"""

TEAM_NAME_MAPPING = {
    # 英超
    "富勒姆": "Fulham",
    "纽卡斯尔": "Newcastle",
    "纽卡斯尔联": "Newcastle United",
    "水晶宫": "Crystal Palace",
    "阿森纳": "Arsenal",
    "利物浦": "Liverpool",
    "布伦特": "Brentford",
    "布伦特福德": "Brentford",
    "曼城": "Manchester City",
    "曼城队": "Manchester City",
    "维拉": "Aston Villa",
    "阿斯顿维拉": "Aston Villa",
    "纽卡斯尔联队": "Newcastle United",
    "纽卡": "Newcastle United",
    "布莱顿": "Brighton",
    "布莱顿霍夫": "Brighton and Hove Albion",
    "西汉姆": "West Ham",
    "西汉姆联": "West Ham United",
    "热刺": "Tottenham",
    "托特纳姆": "Tottenham",
    "托特纳姆热刺": "Tottenham Hotspur",
    "切尔西": "Chelsea",
    "曼联": "Manchester United",
    "曼彻斯特联": "Manchester United",
    "埃弗顿": "Everton",
    "诺丁汉森林": "Nottingham Forest",
    "狼队": "Wolverhampton Wanderers",
    "伯恩利": "Burnley",
    "谢菲尔德联": "Sheffield United",
    "卢顿": "Luton Town",
    "伯恩茅斯": "Bournemouth",
    "南安普顿": "Southampton",
    "莱斯特城": "Leicester City",
    "沃特福德": "Watford",
    "利兹联": "Leeds United",
    "伊普斯维奇": "Ipswich Town",
    "伊普斯维奇镇": "Ipswich Town",
    "莱斯特": "Leicester City",
    "埃弗顿队": "Everton",
    "伯恩利队": "Burnley",

    # 意甲
    "莱切": "Lecce",
    "热那亚": "Genoa",
    "帕尔马": "Parma",
    "萨索洛": "Sassuolo",
    "罗马": "Roma",
    "AS罗马": "Roma",
    "那不勒斯": "Napoli",
    "拿玻里": "Napoli",
    "亚特兰大": "Atalanta",
    "尤文图斯": "Juventus",
    "尤文": "Juventus",
    "国米": "Inter Milan",
    "国际米兰": "Inter Milan",
    "AC米兰": "AC Milan",
    "米兰": "AC Milan",
    "拉齐奥": "Lazio",
    "佛罗伦萨": "Fiorentina",
    "紫百合": "Fiorentina",
    "都灵": "Torino",
    "乌迪内斯": "Udinese",
    "博洛尼亚": "Bologna",
    "卡利亚里": "Cagliari",
    "恩波利": "Empoli",
    "蒙扎": "Monza",
    "维罗纳": "Hellas Verona",
    "科莫": "Como",
    "威尼斯": "Venezia",
    "莱切队": "Lecce",
    "热那亚队": "Genoa",

    # 西甲
    "马德里竞技": "Atletico Madrid",
    "马竞": "Atletico Madrid",
    "塞维利亚": "Sevilla",
    "皇家社会": "Real Sociedad",
    "皇社": "Real Sociedad",
    "比利亚雷亚尔": "Villarreal",
    "黄潜": "Villarreal",
    "皇家贝蒂斯": "Real Betis",
    "贝蒂斯": "Real Betis",
    "毕尔巴鄂竞技": "Athletic Bilbao",
    "毕尔巴鄂": "Athletic Bilbao",
    "瓦伦西亚": "Valencia",
    "巴塞罗那": "Barcelona",
    "皇家马德里": "Real Madrid",
    "皇马": "Real Madrid",
    "巴萨": "Barcelona",
    "赫罗纳": "Girona",
    "赫塔菲": "Getafe",
    "赫塔费": "Getafe",
    "奥萨苏纳": "Osasuna",
    "塞尔塔": "Celta Vigo",
    "维戈塞尔塔": "Celta Vigo",
    "巴列卡诺": "Rayo Vallecano",
    "拉斯帕尔马斯": "Las Palmas",
    "阿拉维斯": "Alaves",
    "格拉纳达": "Granada",
    "加的斯": "Cadiz",
    "马洛卡": "Mallorca",
    "埃瓦尔": "Eibar",

    # 德甲
    "勒沃库森": "Bayer Leverkusen",
    "药厂": "Bayer Leverkusen",
    "沃尔夫斯堡": "Wolfsburg",
    "狼堡": "Wolfsburg",
    "法兰克福": "Eintracht Frankfurt",
    "多特蒙德": "Borussia Dortmund",
    "多特": "Borussia Dortmund",
    "拜仁": "Bayern Munich",
    "拜仁慕尼黑": "Bayern Munich",
    "莱比锡": "RB Leipzig",
    "莱比锡红牛": "RB Leipzig",
    "斯图加特": "VfB Stuttgart",
    "弗赖堡": "Freiburg",
    "门兴": "Borussia Monchengladbach",
    "门兴格拉德巴赫": "Borussia Monchengladbach",
    "霍芬海姆": "Hoffenheim",
    "柏林联合": "Union Berlin",
    "柏林赫塔": "Hertha Berlin",
    "美因茨": "Mainz 05",
    "科隆": "FC Cologne",
    "达姆施塔特": "Darmstadt 98",
    "海登海姆": "Heidenheim",
    "波鸿": "Bochum",
    "奥格斯堡": "Augsburg",
    "不莱梅": "Werder Bremen",
    "云达不莱梅": "Werder Bremen",
    "沙尔克04": "Schalke 04",

    # 法甲
    "摩纳哥": "Monaco",
    "里昂": "Lyon",
    "马赛": "Marseille",
    "巴黎": "Paris Saint-Germain",
    "巴黎圣日耳曼": "Paris Saint-Germain",
    "大巴黎": "Paris Saint-Germain",
    "里尔": "Lille",
    "尼斯": "Nice",
    "朗斯": "Lens",
    "雷恩": "Rennes",
    "图卢兹": "Toulouse",
    "南特": "Nantes",
    "蒙彼利埃": "Montpellier",
    "斯特拉斯堡": "Strasbourg",
    "兰斯": "Reims",
    "洛里昂": "Lorient",
    "克莱蒙": "Clermont",
    "勒阿弗尔": "Le Havre",
    "梅斯": "Metz",
    "布雷斯特": "Brest",
    "欧塞尔": "Auxerre",

    # 中超 (Chinese Super League)
    "上海海港": "Shanghai Port",
    "上海上港": "Shanghai Port",
    "山东泰山": "Shandong Taishan",
    "山东鲁能": "Shandong Taishan",
    "北京国安": "Beijing Guoan",
    "上海申花": "Shanghai Shenhua",
    "广州队": "Guangzhou FC",
    "广州恒大": "Guangzhou FC",
    "成都蓉城": "Chengdu Rongcheng",
    "浙江": "Zhejiang FC",
    "浙江队": "Zhejiang FC",
    "河南": "Henan FC",
    "河南建业": "Henan FC",
    "天津津门虎": "Tianjin Jinmen Tiger",
    "天津泰达": "Tianjin Jinmen Tiger",
    "长春亚泰": "Changchun Yatai",
    "武汉三镇": "Wuhan Three Towns",
    "北京人和": "Beijing Renhe",
    "深圳队": "Shenzhen FC",
    "深圳佳兆业": "Shenzhen FC",
    "大连人": "Dalian Pro",
    "大连一方": "Dalian Pro",
    "沧州雄狮": "Cangzhou Mighty Lions",
    "青岛海牛": "Qingdao Hainiu",
    "梅州客家": "Meizhou Hakka",
    "南通支云": "Nantong Zhiyun",
    "武汉长江": "Wuhan Yangtze River",
    "武汉卓尔": "Wuhan Yangtze River",
    "河北队": "Hebei FC",
    "河北华夏幸福": "Hebei FC",
    "重庆两江竞技": "Chongqing Liangjiang Athletic",
    "重庆当代": "Chongqing Liangjiang Athletic",
    "青岛西海岸": "Qingdao West Coast",
    "辽宁铁人": "Liaoning Tieren",
    "四川九牛": "Sichuan Jiuniu",
    "深圳新鹏城": "Shenzhen Xinpengcheng",

    # J-League (日本职业联赛)
    "川崎前锋": "Kawasaki Frontale",
    "横滨水手": "Yokohama F. Marinos",
    "浦和红钻": "Urawa Red Diamonds",
    "鹿岛鹿角": "Kashima Antlers",
    "名古屋鲸鱼": "Nagoya Grampus",
    "清水鼓动": "Shimizu S-Pulse",
    "大阪钢巴": "Gamba Osaka",
    "大阪樱花": "Cerezo Osaka",
    "东京FC": "FC Tokyo",
    "水户蜀葵": "Mito HollyHock",
    "湘南海洋": "Shonan Bellmare",
    "柏太阳神": "Kashiwa Reysol",
    "广岛三箭": "Sanfrecce Hiroshima",

    # K-League (韩国职业联赛)
    "全北现代": "Jeonbuk Hyundai Motors",
    "蔚山现代": "Ulsan Hyundai",
    "首尔FC": "FC Seoul",
    "首尔": "FC Seoul",
    "大邱FC": "Daegu FC",
    "浦项制铁": "Pohang Steelers",
    "水原三星": "Suwon Samsung Bluewings",
    "仁川联": "Incheon United",

    # MLS (美国职业大联盟)
    "洛杉矶银河": "LA Galaxy",
    "LA银河": "LA Galaxy",
    "迈阿密国际": "Inter Miami",
    "国际迈阿密": "Inter Miami",
    "亚特兰大联": "Atlanta United",
    "洛杉矶FC": "Los Angeles FC",

    # 英冠/英甲
    "博尔顿": "Bolton",
    "斯托克港": "Stockport County",
    "桑德兰": "Sunderland",
    "利兹联": "Leeds United",

    # 瑞典超
    "哈马比": "Hammarby",
    "索尔纳": "AIK",
    "天狼星": "Sirius",
    "盖斯": "GAIS",
    "马尔默": "Malmo FF",
    "韦斯特罗": "Vasteras SK",

    # 挪威超
    "博德闪耀": "Bodo/Glimt",
    "布兰": "Brann",
    "罗森博格": "Rosenborg",
    "莫尔德": "Molde",
}

def normalize_team_name(name: str) -> str:
    """标准化球队名称用于匹配"""
    # 移除常见后缀
    suffixes = ["队", "FC", "CF", "United", "City"]
    name = name.strip()
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)].strip()
    return name.lower()

def match_team_name(cn_name: str, en_name: str) -> bool:
    """匹配中英文球队名称"""
    # 直接映射匹配
    if cn_name in TEAM_NAME_MAPPING:
        mapped = TEAM_NAME_MAPPING[cn_name]
        if mapped.lower() in en_name.lower() or en_name.lower() in mapped.lower():
            return True

    # 标准化后包含匹配
    cn_norm = normalize_team_name(cn_name)
    en_norm = normalize_team_name(en_name)

    # 中文名包含在英文名中，或反之
    if cn_norm in en_norm or en_norm in cn_norm:
        return True

    # 部分匹配（如 "Manchester" 匹配 "Man"）
    if len(cn_norm) >= 4 and cn_norm[:4] in en_norm:
        return True
    if len(en_norm) >= 4 and en_norm[:4] in cn_norm:
        return True

    return False


# 联赛名称映射
LEAGUE_NAME_MAPPING = {
    "英超": "Premier League",
    "英格兰超级联赛": "Premier League",
    "EPL": "Premier League",
    "西甲": "La Liga",
    "西班牙甲级联赛": "La Liga",
    "德甲": "Bundesliga",
    "德国甲级联赛": "Bundesliga",
    "意甲": "Serie A",
    "意大利甲级联赛": "Serie A",
    "法甲": "Ligue 1",
    "法国甲级联赛": "Ligue 1",
    "中超": "Chinese Super League",
    "中国足球协会超级联赛": "Chinese Super League",
    "CSL": "Chinese Super League",
    "日职": "J-League",
    "日职联": "J-League",
    "J联赛": "J-League",
    "J1联赛": "J-League",
    "日本职业联赛": "J-League",
    "K联赛": "K-League",
    "K1联赛": "K-League",
    "韩职": "K-League",
    "韩国职业联赛": "K-League",
    "MLS": "MLS",
    "美职联": "MLS",
    "美国职业大联盟": "MLS",
    "欧冠": "Champions League",
    "欧洲冠军联赛": "Champions League",
    "欧联杯": "Europa League",
    "欧罗巴联赛": "Europa League",
    "欧协联": "Europa Conference League",
    "欧洲协会联赛": "Europa Conference League",
    "英冠": "Championship",
    "英格兰冠军联赛": "Championship",
    "英甲": "League One",
    "英格兰甲级联赛": "League One",
    "英乙": "League Two",
    "英格兰乙级联赛": "League Two",
    "瑞典超": "Allsvenskan",
    "瑞典超级联赛": "Allsvenskan",
    "挪威超": "Eliteserien",
    "挪威超级联赛": "Eliteserien",
    "丹超": "Danish Superliga",
    "丹麦超级联赛": "Danish Superliga",
    "荷甲": "Eredivisie",
    "荷兰甲级联赛": "Eredivisie",
    "比甲": "Belgian Pro League",
    "比利时甲级联赛": "Belgian Pro League",
    "葡超": "Primeira Liga",
    "葡萄牙超级联赛": "Primeira Liga",
    "土超": "Super Lig",
    "土耳其超级联赛": "Super Lig",
    "俄超": "Russian Premier League",
    "俄罗斯超级联赛": "Russian Premier League",
    "乌超": "Ukrainian Premier League",
    "乌克兰超级联赛": "Ukrainian Premier League",
    "希腊超": "Super League Greece",
    "希腊超级联赛": "Super League Greece",
    "苏超": "Scottish Premiership",
    "苏格兰超级联赛": "Scottish Premiership",
    "奥超": "Austrian Bundesliga",
    "奥地利超级联赛": "Austrian Bundesliga",
    "瑞士超": "Swiss Super League",
    "瑞士超级联赛": "Swiss Super League",
    "巴甲": "Brasileirao",
    "巴西甲级联赛": "Brasileirao",
    "阿甲": "Argentine Primera Division",
    "阿根廷甲级联赛": "Argentine Primera Division",
    "墨超": "Liga MX",
    "墨西哥超级联赛": "Liga MX",
}


def normalize_league_name(name: str) -> str:
    """标准化联赛名称"""
    if name in LEAGUE_NAME_MAPPING:
        return LEAGUE_NAME_MAPPING[name]
    return name


def team_to_chinese(en_name: str) -> str:
    """将英文名称转换为中文"""
    for cn, en in TEAM_NAME_MAPPING.items():
        if en.lower() == en_name.lower() or en_name.lower() in en.lower():
            return cn
    return en_name


def league_to_chinese(en_name: str) -> str:
    """将联赛英文名称转换为中文"""
    for cn, en in LEAGUE_NAME_MAPPING.items():
        if en.lower() == en_name.lower() or en_name.lower() in en.lower():
            return cn
    return en_name
