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

    # 意甲
    "莱切": "Lecce",
    "热那亚": "Genoa",
    "帕尔马": "Parma",
    "萨索洛": "Sassuolo",
    "罗马": "Roma",
    "AS罗马": "Roma",
    "那不勒斯": "Napoli",
    "亚特兰大": "Atalanta",
    "尤文图斯": "Juventus",
    "国米": "Inter Milan",
    "国际米兰": "Inter Milan",
    "AC米兰": "AC Milan",
    "拉齐奥": "Lazio",
    "佛罗伦萨": "Fiorentina",
    "都灵": "Torino",

    # 西甲
    "马德里竞技": "Atletico Madrid",
    "马竞": "Atletico Madrid",
    "塞维利亚": "Sevilla",
    "皇家社会": "Real Sociedad",
    "比利亚雷亚尔": "Villarreal",
    "皇家贝蒂斯": "Real Betis",
    "毕尔巴鄂竞技": "Athletic Bilbao",
    "瓦伦西亚": "Valencia",
    "巴塞罗那": "Barcelona",
    "皇家马德里": "Real Madrid",
    "皇马": "Real Madrid",
    "巴萨": "Barcelona",
    "赫罗纳": "Girona",

    # 德甲
    "勒沃库森": "Bayer Leverkusen",
    "沃尔夫斯堡": "Wolfsburg",
    "法兰克福": "Eintracht Frankfurt",
    "多特蒙德": "Borussia Dortmund",
    "拜仁": "Bayern Munich",
    "拜仁慕尼黑": "Bayern Munich",
    "莱比锡": "RB Leipzig",
    "斯图加特": "VfB Stuttgart",
    "弗赖堡": "Freiburg",
    "门兴": "Borussia Monchengladbach",
    "门兴格拉德巴赫": "Borussia Monchengladbach",
    "沃尔夫斯堡": "Wolfsburg",

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

    # 中超 (Chinese Super League)
    "上海海港": "Shanghai Port",
    "山东泰山": "Shandong Taishan",
    "北京国安": "Beijing Guoan",
    "上海申花": "Shanghai Shenhua",
    "广州队": "Guangzhou FC",
    "成都蓉城": "Chengdu Rongcheng",
    "浙江": "Zhejiang FC",
    "河南": "Henan FC",
    "天津津门虎": "Tianjin Jinmen Tiger",
    "长春亚泰": "Changchun Yatai",
    "武汉三镇": "Wuhan Three Towns",
    "北京人和": "Beijing Renhe",
    "深圳队": "Shenzhen FC",
    "大连人": "Dalian Pro",
    "沧州雄狮": "Cangzhou Mighty Lions",
    "青岛海牛": "Qingdao Hainiu",
    "梅州客家": "Meizhou Hakka",
    "南通支云": "Nantong Zhiyun",

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
    "EPL": "Premier League",
    "西甲": "La Liga",
    "德甲": "Bundesliga",
    "意甲": "Serie A",
    "法甲": "Ligue 1",
    "中超": "Chinese Super League",
    "CSL": "Chinese Super League",
    "日职": "J-League",
    "J联赛": "J-League",
    "J1联赛": "J-League",
    "K联赛": "K-League",
    "K1联赛": "K-League",
    "MLS": "MLS",
    "美职联": "MLS",
    "欧冠": "Champions League",
    "欧联杯": "Europa League",
    "欧协联": "Europa Conference League",
    "英冠": "Championship",
    "瑞典超": "Allsvenskan",
    "挪威超": "Eliteserien",
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
