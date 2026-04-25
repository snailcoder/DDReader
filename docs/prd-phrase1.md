# 发行人基础信息

## 定义
公司名称、统一社会信用代码或注册号、注册地址、法定代表人、成立日期、注册资本、所属行业，schema如下：
```json
{
    "issuer_profile":{
        "issuer_name":"",  // 公司名称
        "issuer_name_normalized":"", 
        "stock_code":"",
        "exchange":"",
        "board":"",
        "legal_representative":"",  // 法定代表人
        "establishment_date":"",  // 成立日期
        "registered_capital":{  // 注册资本
            "value":null,
            "unit":"万元",
            "currency":"CNY"
        },
        "registered_address":"",  // 注册地址
        "industry":"",  // 所属行业
        "main_business":"",  // 主营业务
        "source_evidence_id":""
    }
}
```

## 分布
- 招股说明书
  - 一级标题：概览，二级标题列举如下：
    1. 一、发行人及本次发行的中介机构基本情况（例如：000064_20190611_31LJ_867634ab，001363_20230217_BU2P_8eda21e9）
    2. 二、本次发行的有关当事人基本情况（例如：002172_20251231_CZB6_e50e6849）
    3. 二、发行人及本次发行的中介机构基本情况（例如：1219066981_ddd76b66，1219089712_645f71b8，1219146278_9d20ba36）
    4. 二、发行人及中介机构情况（例如：1219089320_1ec1d8d7，1219359281_d33ed9bd）

    <img width="400" height="400" alt="image" src="https://github.com/user-attachments/assets/caed8977-c966-4a73-bea6-926221eaeaad" />

    <img width="400" height="400" alt="image" src="https://github.com/user-attachments/assets/dadcf3b5-5672-47af-b3e9-1848022e564c" />

    <img width="400" height="400" alt="image" src="https://github.com/user-attachments/assets/b7ed903c-c438-4003-a86a-8cb707cd1318" />

    <img width="400" height="400" alt="image" src="https://github.com/user-attachments/assets/6e2492c9-397f-4fe4-b097-e3dadea27e66" />

  - 一级标题：发行人基本情况，二级标题列举如下：
    1. 一、发行人基本情况（例如：1219359281_d33ed9bd，001363_20230217_BU2P_8eda21e9）
    2. 一、发行人概况（例如：000064_20190611_31LJ_867634ab）
    3. 一、发行人的基本信息（例如：1219089320_1ec1d8d7）

    <img width="400" height="400" alt="image" src="https://github.com/user-attachments/assets/e60a8726-8910-42f9-9c93-1a05830b06bb" />

    <img width="400" height="400" alt="image" src="https://github.com/user-attachments/assets/719dac71-2fe1-423f-b304-a0e66831f73a" />

    <img width="400" height="400" alt="image" src="https://github.com/user-attachments/assets/9d685da5-2abe-4faa-99b1-b6bef672c641" />

    <img width="400" height="400" alt="image" src="https://github.com/user-attachments/assets/f89563b6-55c1-426d-b25f-3d9b49c8ee0b" />

- 招股说明书提示性公告：无

# 股权与控制关系
## 定义
控股股东、实际控制人、持股比例、是否存在一致行动关系，schema如下：

```json
{
    "ownership_structure":{
        "controlling_shareholder":[  // 控股股东
            {
                "name":"",
                "shareholding_ratio":23.56,  // 持股比例
                "direct_or_indirect":"",
                "source_evidence_id":""
            }
        ],
        "actual_controller":[  // 实际控制人
            {
                "name":"",
                "control_type":"",
                "source_evidence_id":""
            }
        ],
        "concerted_action_flag":false,
        "top_shareholders":[
            {
                "name":"",
                "shareholding_ratio":null,
                "rank":1,
                "source_evidence_id":""
            }
        ]
    }
}

```
## 分布
- 招股说明书
  - 一级标题：发行人基本情况，二级标题列举如下：
    1. 七、持有发行人 5%以上股份或表决权的主要股东及实际控制人的基本情况（例如：1221409205_d7c33543）
    2. 七、持有公司5%以上股份的主要股东、实际控制人的基本情况（例如：1221368038_20f69354）
    3. 八、控股股东及实际控制人、持有发行人5%以上股份的股东（例如：001363_20230217_BU2P_8eda21e9）
    4. 八、公司控股股东、实际控制人及主要股东情况（例如：002172_20251231_CZB6_e50e6849）
    
    <img width="400" height="400" alt="image" src="https://github.com/user-attachments/assets/83d8560b-58d9-4337-8e70-60b2ae52997d" />

    <img width="400" height="400" alt="image" src="https://github.com/user-attachments/assets/90012023-3467-4366-a71a-ce783a45e526" />

    <img width="400" height="400" alt="image" src="https://github.com/user-attachments/assets/94dd5051-d893-4107-951a-fffeb95668fe" />

    <img width="400" height="400" alt="image" src="https://github.com/user-attachments/assets/88e67e6d-59ea-4dc0-8c33-d4b0747f01c8" />

- 招股说明书提示性公告：无

# 财务指标
## 定义
营业收入、净利润、扣非净利润、研发费用、毛利率、资产总额、负债总额、经营活动现金流，schema如下：
```json
{
    "financials":[
        {
            "field_name":"营业收入",
            "field_scope":"合并利润表",
            "period":"2022-12-31",
            "value":123456.78,
            "unit":"万元",
            "currency":"CNY",
            "chapter":"第八节财务会计信息与管理层分析",
            "source_evidence_id":""
        },
        {
            "field_name":"研发费用",
            "field_scope":"研发投入指标",
            "period":"2022-12-31",
            "value":8765.43,
            "unit":"万元",
            "currency":"CNY",
            "chapter":"业务与技术",
            "source_evidence_id":""
        }
    ]
}
```
## 分布
- 招股说明书
  - 一级标题：财务会计信息与管理层分析
  - 二级标题举例
    1. 一、发行人合并财务报表（例如：1221409205_d7c33543）
    2. 一、财务报表（例如：1221368038_20f69354，RAS_202511_281500FBB48014CAC24AA685615E839AA8F20B_0947a61f）
    3. 二、经审计的财务报表（例如：000064_20190611_31LJ_867634ab）
    4. 一、发行人的财务报表（例如：1222129985_bc3c44c1）
    5. 一、发行人报告期内的财务报表（例如：RAS_202511_2816353444FBCE4B4345D0A21C9538BF733B87_4e7ab10a）
    
    <img width="400" height="400" alt="image" src="https://github.com/user-attachments/assets/3844e17d-5538-40f6-94c1-17b1b894962d" />

    <img width="400" height="400" alt="image" src="https://github.com/user-attachments/assets/9d997585-6f83-463f-b46e-22aafa76b19f" />

    <img width="400" height="400" alt="image" src="https://github.com/user-attachments/assets/239865f7-9022-4b2e-8717-7b7911fd1309" />

    <img width="400" height="400" alt="image" src="https://github.com/user-attachments/assets/496b3a01-ede6-45f4-aada-17456e6977fc" />

- 招股说明书提示性公告：无

# 风险事项
## 定义
重大风险因素标题、风险描述、风险类别，schema如下：
```json
{
    "risk_items":[
        {
            "risk_title":"",  //风险标题
            "risk_category":"财务风险",  // 风险类别
            "risk_description":"",  // 风险描述
            "severity_level":"中",
            "source_evidence_id":""
        }
    ]
}
```

## 分布
- 招股说明书
  - 一级标题：风险因素
  - 二级标题举例：
    1. 一、与行业相关的风险（例如：RAS_202506_2715252774F520890E4E8F891303E17BA98751_570a21c1）
    2. 二、与发行人相关的风险 （例如：RAS_202506_2715252774F520890E4E8F891303E17BA98751_570a21c1）
    3. 三、其他风险（例如：RAS_202506_2715252774F520890E4E8F891303E17BA98751_570a21c1）

    <img width="400" height="400" alt="image" src="https://github.com/user-attachments/assets/8514fcb2-6bf0-4802-987d-ab43bc53855a" />

    <img width="400" height="400" alt="image" src="https://github.com/user-attachments/assets/856aee7b-5dde-40ff-936b-c8245c55e772" />

    <img width="400" height="400" alt="image" src="https://github.com/user-attachments/assets/3844fcfd-22f8-4557-8ef1-e6e00f5d08ff" />

- 招股说明书提示性公告：无

# 募资用途
## 定义
项目名称、项目投资总额、拟使用募集资金金额、建设周期，schema如下：
```json
{
    "fund_raising_projects":[
        {
            "project_name":"",
            "project_type":"扩产",
            "total_investment":{  // 投资总额
                "value":null,
                "unit":"万元",
                "currency":"CNY"
            },
            "planned_use_of_raised_funds":{  // 拟使用募集资金金额
                "value":null,
                "unit":"万元",
                "currency":"CNY"
            },
            "construction_period":"",  // 建设周期
            "implementation_entity":"",
            "source_evidence_id":""
        }
    ]
}
```

## 分布
- 招股说明书
  - 一级标题举例：
    1. 第七节  募集资金运用及未来发展规划（例如：RAS_202506_2715252774F520890E4E8F891303E17BA98751_570a21c1）
    2. 第七节  募集资金运用与未来发展规划（例如：RAS_202409_282150B8CF03B3660C4DB4A3F82B1950C4B0CF_ae254da7，1225019967_bd6af848）
  - 二级标题举例：
    1. 一、本次募集资金投资项目概况（例如：RAS_202506_2715252774F520890E4E8F891303E17BA98751_570a21c1）
    2. 一、募集资金运用情况（例如：RAS_202403_131505164EF5133F204F01AC6581E9B2DC9426_f12cc361）
    3. 一、募集资金运用概况（例如：225019967_bd6af848）
    4. 一、本次募集资金运用情况（例如：RAS_202409_282150B8CF03B3660C4DB4A3F82B1950C4B0CF_ae254da7）
    5. 一、募集资金基本情况（例如：1225019140_e2b54cee）
    
    <img width="400" height="400" alt="image" src="https://github.com/user-attachments/assets/87cb9a84-a02f-40e7-96b0-4ff2711dfbae" />

    <img width="400" height="400" alt="image" src="https://github.com/user-attachments/assets/922a2490-90ec-4a20-909b-c2228fc66e03" />

    <img width="400" height="400" alt="image" src="https://github.com/user-attachments/assets/99e02c4a-5942-4fb1-bbfa-0e081aae85af" />

    <img width="400" height="400" alt="image" src="https://github.com/user-attachments/assets/fd86761b-afa8-4865-9d27-0a00e9db243e" />

- 招股说明书提示性公告：无

# 合规事项
## 定义
处罚、诉讼仲裁、关联交易、对外担保，schema如下：
```json
{
    "compliance_items":[
        {
            "item_type":"行政处罚",
            "counterparty":"",
            "occurrence_date":"",
            "amount":{
                "value":null,
                "unit":"万元",
                "currency":"CNY"
            },
            "description":"",
            "source_evidence_id":""
        },
        {
            "item_type":"关联交易",
            "counterparty":"",
            "period":"2022-12-31",
            "amount":{
                "value":null,
                "unit":"万元",
                "currency":"CNY"
            },
            "description":"",
            "source_evidence_id":""
        }
    ]
}
```

## 分布
- 招股说明书
  - 一级标题举例：
    1. 第十节  其他重要事项
  - 二级标题举例：
    1. 一、重大合同（例如：1224969398_10f9d706，1224992124_40906cd6，1225019140_e2b54cee，RAS_202403_131505164EF5133F204F01AC6581E9B2DC9426_f12cc361）
    2. 一、重要合同 （例如：1225019967_bd6af848）
    3. 二、对外担保情况（例如：RAS_202409_282150B8CF03B3660C4DB4A3F82B1950C4B0CF_ae254da7，1225019967_bd6af848）
    4. 二、对外担保 （例如：1225019140_e2b54cee）
    5. 三、重大诉讼、仲裁及立案调查事项（例如：RAS_202409_282150B8CF03B3660C4DB4A3F82B1950C4B0CF_ae254da7）
    6. 三、重大诉讼或仲裁情况（例如：RAS_202506_2715252774F520890E4E8F891303E17BA98751_570a21c1，RAS_202403_131505164EF5133F204F01AC6581E9B2DC9426_f12cc361，1224967419_d0df76ff）
    7. 三、重大诉讼及仲裁事项 （例如：1225019967_bd6af848，1224992124_40906cd6）
    8. 三、重大诉讼或仲裁事项（例如：1224969398_10f9d706）

    <img width="400" height="400" alt="image" src="https://github.com/user-attachments/assets/19079c3e-a57e-4597-a7df-d2c30270dca6" />

    <img width="400" height="400" alt="image" src="https://github.com/user-attachments/assets/724ff3b1-0a33-4cff-a654-799fe667912e" />

    <img width="400" height="400" alt="image" src="https://github.com/user-attachments/assets/1f6ba57a-f683-4416-b3e9-e0ba9015d94f" />

    <img width="400" height="400" alt="image" src="https://github.com/user-attachments/assets/f2a65e7b-21f0-4daf-9c6b-a373fec3d82c" />

    <img width="400" height="400" alt="image" src="https://github.com/user-attachments/assets/4a2fc5e8-4a69-46cc-8de8-46ce250e77d8" />

- 招股说明书提示性公告：无
