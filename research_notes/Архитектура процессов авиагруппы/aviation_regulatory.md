# Авиационные регуляторные и отраслевые требования к системе управления эксплуатанта / вертолётного оператора / ТОиР (сертификационный базис)

Дата сбора: 2026-10-03. Конвенция: в «Cited Findings» — только то, что подтверждено найденным источником (URL); часть источников получена через автоматическое резюме страницы (WebFetch), такие места помечены «(резюме страницы)» — дословный текст нужно сверить. Всё, что взято из общих знаний без подтверждения в этой сессии, вынесено в «Inferences» или «Gaps» с пометкой [не проверено].

## 1. IATA IOSA (ISM) и ISAGO (GOSM): структура дисциплин

### Takeaway
IOSA Standards Manual (ISM) состоит из 8 разделов: ORG, FLT, DSP, MNT, CAB, GRH, CGO, SEC; актуальная редакция по странице IATA — Edition 18 Revision 1 с полностью интегрированной оценкой зрелости (risk-based IOSA). ISAGO с 2025 г. перестроен: GOSM Ed.11, стандарты аудита основаны на IGOM и AHM; модули ORM, TRN, PAX, BAG, RMP, LOD, CGM (CGM заменяется стандартами ICHM с января 2026).

### Cited Findings
- Разделы ISM: Organization and Management Systems (ORG); Flight Operations (FLT); Operational Control and Flight Dispatch (DSP); Aircraft Engineering and Maintenance (MNT); Cabin Operations (CAB); Ground Handling Operations (GRH); Cargo Operations (CGO); Security Management (SEC) — [IATA ISM page](https://www.iata.org/en/publications/manuals/iosa-standard-manual)
- Текущая редакция на странице IATA — ISM Edition 18 Rev 1; «Maturity assessment criteria are now fully integrated»; «Risk-based IOSA delivers an audit scope that will be tailored for each airline»; изменения затрагивают все 8 разделов (в т.ч. Safety Risk Assessment на этапе планирования полёта, ULD/опасные грузы, расширение ссылок по security) (резюме страницы) — [IATA ISM page](https://www.iata.org/en/publications/manuals/iosa-standard-manual)
- Историческая точка: ISM Ed.16 Rev 2 действовала с 1 ноября 2023 (по резюме поиска; страница репозитория IATA по Ed.16) — [IATA repository ISM Ed16](https://www.iata.org/en/iata-repository/publications/iosa-audit-documentation/iosa-standards-manual-ism-ed-16-rev-11)
- ISAGO: GOSM Edition 11 выпускается в 2025 и заменяет Ed.10 v1, использовавшуюся ~4 года; «the requirements used for future ISAGO audits (Q2 2025 and onwards) will be fully based on IGOM and IATA Airport Handling Manual (AHM) provisions»; документальная часть — удалённо через портал, на месте — проверка внедрения IGOM/AHM; GHSP должны принять стандарт обучения AHM 1110 — [AviationPros: The Difference Between IGOM and ISAGO](https://www.aviationpros.com/ground-handling/article/55246951/the-difference-between-igom-and-isago)
- Модули ISAGO и их база: ORM (Organizational & Management) — AHM 600; TRN (Training) — AHM 1110; PAX — IGOM гл.1; BAG — IGOM гл.2; RMP (Ramp) — IGOM гл.3–4; LOD (Load Control) — IGOM гл.5; CGM (Cargo & Mail) — GOSM Ed10 Rev1, с января 2026 заменяется стандартами ICHM (по резюме поиска) — [IATA ISAGO](https://www.iata.org/en/programs/safety/audit/isago/); [IATA презентация 2025-09-25](https://www.iata.org/contentassets/e28d00ea3ba54be5a9ec5b34347d1c22/20250925_1100_marc-volkl_approved.pdf)

### Inferences
- [не проверено в этой сессии, из общих знаний ISM] Раздел ORG традиционно включает подразделы: Management and Control (в т.ч. Accountable Executive, распределение ответственности), Management Review, Documentation & Records (контроль документов), Safety Management (SMS по Annex 19), Quality Assurance / Oversight программы, Outsourcing (контроль внешних поставщиков), Emergency Response. Именно ORG — «зонтик» для процессов управления уровня 1; FLT/DSP/MNT/CAB/GRH/CGO/SEC — производственные дисциплины, хорошо ложащиеся на основные процессы L1.
- Для группы: IOSA проходит авиакомпания (держатель AOC); MNT/GRH/CGO, выполняемые сестринскими компаниями, проверяются через требования ORG/каждой дисциплины к контролю аутсорсинга — сам провайдер не становится «IOSA-сертифицированным».
- ISAGO применим к провайдеру наземного обслуживания (GHSP) как к отдельному юрлицу — естественный кандидат на собственную архитектуру процессов в группе.

### Gaps
- Точный перечень подразделов ORG в Ed.18 и дата вступления Ed.18 Rev 1 / наличие Ed.19 в 2026 — открытый текст ISM за paywall/скачиванием, не получен.
- Содержание модуля ORM (AHM 600) по пунктам не проверено.

## 2. ICAO: Annex 19 / Doc 9859 (SMS), Annex 6 Part I/III, Annex 8

### Takeaway
Каркас SMS ICAO — 4 компонента / 12 элементов (Annex 19 App. 2; Doc 9859). Он же воспроизведён в ORO.GEN.200 EASA и в российском ПП РФ №642 (по смыслу). Конкретные тексты Annex 6 Part III и Annex 8 в этой сессии не проверялись.

### Cited Findings
- Каркас SMS: 1. Safety policy and objectives — 1.1 Management commitment; 1.2 Safety accountability and responsibilities; 1.3 Appointment of key safety personnel; 1.4 Coordination of emergency response planning; 1.5 SMS documentation. 2. Safety risk management — 2.1 Hazard identification; 2.2 Safety risk assessment and mitigation. 3. Safety assurance — 3.1 Safety performance monitoring and measurement; 3.2 The management of change; 3.3 Continuous improvement of the SMS. 4. Safety promotion — 4.1 Training and education; 4.2 Safety communication — [ICAO NACC презентация SMS](https://www.icao.int:443/NACC/Documents/Meetings/2016/ACI/D2-06SMS.pdf); [SAS: 12 elements of ICAO SMS](https://sassofia.com/blog/understanding-the-12-elements-of-the-icao-sms-framework/)

### Inferences
- [не проверено] Doc 9859 4-е издание — 2018; Annex 19 2-е издание — 2016 (применимо с 2019). Названия элементов в 4-м издании формулируются как выше (в 3-м изд. «Management commitment and responsibility» было объединено) — сверить.
- [не проверено] Annex 6 Part III (вертолёты), Section II (international commercial air transport) содержит требования к operational control, SMS (ссылка на Annex 19), maintenance responsibilities оператора; Annex 8 возлагает continuing airworthiness на государство регистрации и на эксплуатанта. Для архитектуры L1 это означает: «Управление поддержанием лётной годности» — обязанность эксплуатанта, даже если ТО выполняет сестринская АТБ.
- 12 элементов SMS удобно использовать как чек-лист покрытия процессов управления L1 (политика, ответственность, ERP, документация, управление рисками, мониторинг показателей, управление изменениями, обучение, коммуникации).

### Gaps
- Не получен первоисточник icao.int с текстом Annex 19 App.2 (документ платный/ограниченный); элементы подтверждены презентацией ICAO регионального офиса и вторичным источником.
- Требования Annex 6 Part III к operational control и Annex 8 — не проверены по тексту.

## 3. EASA: Part-ORO, Part-CAMO, Part-145; интегрированная система управления

### Takeaway
EASA строит систему управления держателя AOC на ORO.GEN.200 (management system), ORO.GEN.205 (contracted activities), ORO.GEN.210 (accountable manager + nominated persons) и ORO.AOC.135 (4 nominated persons: flight operations, crew training, ground operations, continuing airworthiness). Part-CAMO (CAMO.A.305) и Part-145 (145.A.30, 145.A.200) после Reg. (EU) 2021/1963 приведены к той же SMS-модели: AM + nominated persons + compliance monitoring manager + safety manager. EASA прямо допускает интегрированную систему управления, когда одна организация держит несколько допусков.

### Cited Findings
- Easy Access Rules for Air Operations — Revision 24, март 2026 (резюме страницы) — [EASA EAR Air Ops](https://www.easa.europa.eu/en/document-library/easy-access-rules/online-publications/easy-access-rules-air-operations)
- ORO.GEN.200 требует системы управления, включающей: чётко определённые линии ответственности и подотчётности; safety policy; идентификацию угроз и оценку/управление рисками; обученный и компетентный персонал; документирование процессов системы управления; функцию мониторинга соответствия (compliance monitoring) (резюме поиска) — [EASA AMC&GM Part-ORO Amdt 29, ED Decision 2025/020/R](https://www.easa.europa.eu/en/downloads/142838/en)
  - Расхождение: резюме страницы EAR Rev.24 даёт другую формулировку (a)(1)–(6): safety policy; organisational structure; safety risk management process; safety assurance processes; safety promotion; occurrence reporting system — [EASA EAR Air Ops](https://www.easa.europa.eu/en/document-library/easy-access-rules/online-publications/easy-access-rules-air-operations). Не ясно, отражает ли это реальную поправку ORO.GEN.200 (выравнивание с Annex 19) или ошибку резюмирования — требует сверки с EUR-Lex.
- В 2025 изменены AMC1 ORO.GEN.200(a)(1) (safety action plans, роль safety manager в инициировании внутренних расследований, участие в Safety Review Board) и AMC1 ORO.GEN.200(a)(3) (complex operators — safety risk management) — [ED Decision 2025/020/R, AMC&GM Part-ORO Issue 2 Amdt 29](https://www.easa.europa.eu/en/downloads/142838/en)
- ORO.GEN.205: оператор остаётся ответственным за то, чтобы подрядчики выполняли применимые требования (резюме страницы) — [EASA EAR Air Ops](https://www.easa.europa.eu/en/document-library/easy-access-rules/online-publications/easy-access-rules-air-operations)
- ORO.AOC.135: «In accordance with ORO.GEN.210(b), the operator shall nominate persons responsible for the management and supervision of: flight operations; crew training; ground operations; continuing airworthiness [или контракт на управление ПЛГ]» (резюме поиска) — [UK CAA Regulatory Library ORO.AOC.135](https://regulatorylibrary.caa.co.uk/965-2012/Content/Regs/02720_OROAOC135_Personnel_requirements.htm); [EASA ERULES](https://www.easa.europa.eu/en/easy-access-rules/4e4220/ERULES-1963177438-12102)
- AMC к ORO.AOC.135: NP по flight ops / crew training / ground ops — практический опыт, знание правил ЕС, OM и спецификаций, знакомство с системами управления, 5 лет релевантного опыта (≥2 года в авиаотрасли); NP flight ops — действующее/бывшее свидетельство пилота; NP crew training или его заместитель — действующий TRI; NP continuing airworthiness — по Reg. (EU) 1321/2014 — [UK CAA GM2 ORO.AOC.135(a)](https://regulatorylibrary.caa.co.uk/965-2012/Content/GM/GM2%20ORO%20AOC%20135%20a%20Personnel.htm); [Sofema: EASA AOC Nominated Persons](https://www.sofemaonline.com/about/news/580-easa-aoc-nominated-persons-training-considerations)
- CAMO.A.305: accountable manager с корпоративными полномочиями финансировать и обеспечивать ПЛГ-деятельность; AM назначает лицо/группу (i) за соответствие требованиям управления ПЛГ, airworthiness review и permit to fly; (ii) за функцию compliance monitoring; (iii) за safety management processes; при нескольких лицах в CM — один «compliance monitoring manager», не совмещающий роль из (a)(3); прямой доступ NP к AM — [UK CAA CAMO.A.305](https://regulatorylibrary.caa.co.uk/1321-2014/Content/map2/04870_CAMOA305_Personnel_requirements.htm); [Sofema Part-CAMO competence](https://sofemaonline.com/about/blog/entry/review-of-competence-requirements-related-to-easa-part-camo-regulatory-obligations)
- 145.A.30: AM с корпоративными полномочиями финансировать ТО; обеспечивает ресурсы, устанавливает и продвигает safety policy; назначает лиц, представляющих структуру управления функциями ТО, лиц за compliance monitoring и за safety management; прямой доступ к AM — [UK CAA 145.A.30](https://regulatorylibrary.caa.co.uk/1321-2014/Content/Regs/01644%20145.A.30%20Personnel%20Requirements.htm)
- 145.A.200: система управления — подотчётность и линии ответственности, safety policy, управление угрозами/рисками, компетентный персонал, документирование процессов, функция мониторинга соответствия — [UK CAA 145.A.200](https://regulatorylibrary.caa.co.uk/1321-2014/Content/May%20SI%20New%20Regs/145.A.200%20Management%20system.htm)
- Интегрированная система: когда одна организация держит несколько допусков, её система управления может объединять политики, процедуры и стандарты разных областей в единую структуру, избегая изолированных процедур для общих процессов; «management system» в 1321/2014 — набор взаимосвязанных политик, процедур, стандартов и процессов под общей культурой безопасности; линии ответственности организации-держателя AOC и CAMO связаны напрямую с корпоративными полномочиями AM оператора (резюме поиска, ссылки на AMC/GM Part-CAMO, ED Decision 2022/017/R) — [EASA AMC/GM](https://www.easa.europa.eu/en/print/pdf/node/121040/167449); [SAS: Integrated MSAT multiple certificates](https://sassofia.com/tag/msat-challenges/)

### Inferences
- [не проверено по тексту] 145.A.65 «Safety and quality policy, procedures and quality system» — прежняя (до Reg. 2021/1963, применимой со 2 декабря 2022) основа системы качества 145; теперь функции перенесены в 145.A.200 (management system) и связанные пункты. Аналогично Part-CAMO (Reg. 2019/1383) заменил M.A. Subpart G.
- [не проверено] ORO.GEN.210(a): AM с полномочием обеспечивать финансирование и выполнение всех работ; (b) nominated persons; (c) достаточный квалифицированный персонал. ORO.GEN.205: оператор остаётся ответственным и обеспечивает, что подрядчик соответствует требованиям (через договор + аудит/надзор; AMC допускает учёт сертификата подрядчика).
- Модель «AM + NP» естественно отображается на «владельцев процессов» L1: AM — владелец системы управления (процессы управления), NP Flight Ops — основной процесс «Выполнение полётов», NP Crew Training — «Подготовка экипажей», NP Ground Ops — «Наземное обеспечение», NP CAW/CAMO — «Поддержание ЛГ»; Compliance Monitoring Manager и Safety Manager — владельцы обеспечивающих процессов мониторинга соответствия и SMS, независимые от производства.
- Внутригрупповой аутсорсинг (ТОиР, наземка, ИТ) регуляторно — обычный contracted activity: допустим, но ответственность и контроль (договор, аудит, приёмка) остаются у держателя сертификата; у каждого юрлица-держателя допуска — свой AM, свои NP, своя (возможно общая по платформе) система управления. Общие процессы группы (документооборот, обучение, аудит) можно разделять, но регуляторные функции (CM, SMS) должны быть назначаемы и подотчётны в пределах каждого сертификата.

### Gaps
- Точный текст ORO.GEN.200(a) в действующей консолидации (есть расхождение между двумя резюме) — сверить по EUR-Lex 965/2012 consolidated.
- EASA GM о «combined/integrated management system» по ORO и CAMO/145 — конкретный номер AMC/GM не подтверждён. Part-ORA (ATO) — не исследован.
- Применимость к одной организации одновременно AOC + CAMO (обязательность CAMO для CAT-оператора) — не проверена.

## 4. Российская Федерация: ФАП и СУБП

### Takeaway
Действующие базовые акты: для коммерческих эксплуатантов — ФАП, утв. приказом Минтранса от 12.01.2022 № 10 (с 01.09.2022 до 01.09.2028; изм. приказом № 76 от 04.03.2025), заменил ФАП-246 (2015), который в свою очередь заменил приказ № 11 (2003). Для организаций по ТО — ФАП-109 (приказ Минтранса от 31.03.2023 № 109, с 01.03.2024 до 01.03.2030), заменил ФАП-285. СУБП — ст. 24.1 ВК РФ + ПП РФ от 12.04.2022 № 642 (заменило ПП № 1215 от 18.11.2014).

### Cited Findings
- Приказ Минтранса от 04.02.2003 № 11 «ФАП "Сертификационные требования к эксплуатантам коммерческой гражданской авиации. Процедуры сертификации"» — исторический акт — [legalacts.ru](https://legalacts.ru/doc/prikaz-mintransa-rf-ot-04022003-n-11/)
- Приказ Минтранса от 13.08.2015 № 246 (ФАП «Требования к юрлицам, ИП, осуществляющим коммерческие воздушные перевозки…») утратил силу, заменён приказом от 12.01.2022 № 10; изменения в Приложение № 1 внесены приказом от 04.03.2025 № 76 — [legalacts.ru ФАП-246](https://legalacts.ru/doc/prikaz-mintransa-rossii-ot-13082015-n-246/); [pravo.ppt.ru приказ 76](https://pravo.ppt.ru/prikaz/mintrans/n-76-311411)
- Приказ № 10 от 12.01.2022: зарег. 15.03.2022 № 67758, действует с 01.09.2022 до 01.09.2028 (резюме страницы) — [legalacts.ru приказ 10](https://legalacts.ru/doc/prikaz-mintransa-rossii-ot-12012022-n-10-ob-utverzhdenii/)
- По резюме страницы приказа № 10 (дословно сверить!): п. 4 — разработать и обеспечить функционирование системы управления качеством; п. 5 — руководитель назначает ответственных за: (а) организацию подготовки и допуска к полёту членов экипажей; (б) поддержание лётной годности ВС; (в) функционирование СУБП; (г) авиационную безопасность; (д) функционирование системы управления качеством; (е) наземное обслуживание; ответственные за СУБП и качество подчиняются непосредственно руководителю и независимы от производственной деятельности; п. 7 — требования к СУБП (оргструктура, управление рисками, в т.ч. усталостью, взаимодействие с внешними поставщиками услуг); п. 8 — стаж для ВС с МВМ ≥ 5700 кг (подготовка экипажей — ≥3 лет практики и ≥5 лет КВС; ПЛГ — ≥5 лет; СУБП — ≥5 лет; АБ — ≥3 лет); п. 9 — сниженные требования для лёгких ВС/БАС; п. 43 — допускается организовать ТО сторонними организациями с сертификатами ТО; п. 48 — эксплуатант сохраняет контроль за ТО у подрядчика; п. 50 — наземное обслуживание силами эксплуатанта или по договору — [legalacts.ru приказ 10](https://legalacts.ru/doc/prikaz-mintransa-rossii-ot-12012022-n-10-ob-utverzhdenii/)
- ФАП-109 (приказ Минтранса от 31.03.2023 № 109) — требования к юрлицам/ИП, выполняющим ТО подлежащих сертификации БАС, ВС, двигателей, воздушных винтов (кроме лёгких/сверхлёгких не для коммерции); с 01.03.2024 до 01.03.2030; с 01.03.2024 изменения в сертификаты по ФАП-285 невозможны — [legalacts.ru приказ 109](https://legalacts.ru/doc/prikaz-mintransa-rossii-ot-31032023-n-109-ob-utverzhdenii/); [normacs](https://www.normacs.info/ntds/21358)
- По резюме страницы ФАП-109 (сверить): п. 32 — система контроля качества; п. 33 — СУБП в соответствии с законодательством; п. 37 — назначение лиц, ответственных за обеспечение и контроль качества заявленных работ; п. 38 — требования к персоналу качества устанавливаются в руководстве организации; п. 29 — разработка и утверждение руководства; отдельные должности СУБП/подготовки не названы — [legalacts.ru приказ 109](https://legalacts.ru/doc/prikaz-mintransa-rossii-ot-31032023-n-109-ob-utverzhdenii/)
- ВК РФ ст. 24.1 (введена 260-ФЗ от 25.12.2012): государственная система управления БП реализуется по стандартам ICAO; Правительство устанавливает порядок разработки и применения СУБП для разработчиков, изготовителей, операторов, организаций ТО, АНО и подготовки пилотов — [legalacts.ru ВК ст.24.1](https://legalacts.ru/kodeks/Vozdushnyi-Kodeks-RF/glava-iii/statja-24.1/)
- ПП РФ от 18.11.2014 № 1215 утратило силу; действует ПП РФ от 12.04.2022 № 642 «Правила разработки и применения СУБП воздушных судов, а также сбора и анализа данных о факторах опасности и риска…» — [legalacts.ru ПП 642](https://legalacts.ru/doc/postanovlenie-pravitelstva-rf-ot-12042022-n-642-ob-utverzhdenii/)

### Inferences
- Перечень ответственных лиц п. 5 ФАП-10 — прямой российский аналог EASA NP, плюс АБ и СМК: это готовый «скелет владельцев» процессов L1 для юрлица-эксплуатанта (подготовка экипажей, ПЛГ, СУБП, АБ, качество, наземное обслуживание) под руководителем как аналогом AM.
- В ФАП-109 модель ответственных лиц слабее (качество + СУБП через ПП 642), поэтому для юрлица ТОиР набор владельцев определяется Руководством по деятельности организации.
- Внутригрупповой аутсорсинг ТО и наземного обслуживания допускается ФАП-10 (пп. 43, 48, 50 по резюме) при сохранении контроля эксплуатантом — аналог ORO.GEN.205.

### Gaps
- Дословный текст пп. 4–9, 43, 48, 50 ФАП-10 и пп. 29–39 ФАП-109 — получен через автоматическое резюме; номера пунктов требуют сверки по consultant.ru/garant.ru. Обнаружена возможная неточность: резюме ФАП-109 «не содержит положений о субподряде» — сомнительно, проверить.
- Не проверены: требования к вертолётным эксплуатантам (специфика в ФАП-10/ФАП-128), авиационная безопасность (ФАП-142 и ФЗ-16 «О транспортной безопасности» — номера не проверены), ФАП по подготовке авиаперсонала, ФАП по поддержанию лётной годности/инженерно-авиационному обеспечению.
- Не найден открытый документ ФАВТ о совмещении СМК/СУБП нескольких юрлиц группы.

## 5. AM / nominated persons как «владельцы процессов»; аутсорсинг внутри группы

### Takeaway
И EASA, и ФАП РФ требуют на каждом сертификате одного высшего ответственного (AM / руководитель) и набор назначенных лиц по функциональным областям, плюс независимые функции мониторинга соответствия и SMS. Внутригрупповые поставщики (ТОиР, наземка, ИТ) — это контрактуемая деятельность: разрешена, но ответственность не передаётся.

### Cited Findings
- EASA: оператор остаётся ответственным за соответствие подрядчиков (ORO.GEN.205) — [EASA EAR Air Ops](https://www.easa.europa.eu/en/document-library/easy-access-rules/online-publications/easy-access-rules-air-operations)
- Линии ответственности держателя AOC и CAMO привязаны к корпоративным полномочиям AM оператора — [EASA AMC/GM Part-CAMO](https://www.easa.europa.eu/en/print/pdf/node/121040/167449)
- РФ: ТО силами сторонних организаций с сертификатом, контроль сохраняется за эксплуатантом; наземное обслуживание — по договору (резюме) — [legalacts.ru приказ 10](https://legalacts.ru/doc/prikaz-mintransa-rossii-ot-12012022-n-10-ob-utverzhdenii/)

### Inferences
- Предлагаемое отображение для архитектуры L1 по юрлицу: (1) процесс «Управление системой менеджмента/стратегия» — владелец AM/руководитель; (2) основные процессы — владельцы NP/ответственные лица (полёты, подготовка, наземка, ПЛГ/ТО); (3) обеспечивающие независимые — Compliance Monitoring/СМК и SMS/СУБП (прямой доступ к AM); (4) «Управление внешними поставщиками/контрактуемой деятельностью» — обязателен как отдельный процесс, если в группе есть сервисные сестринские компании.
- Групповые общие сервисы (ИТ, закупки, HR) не являются регулируемыми «contracted activities» в смысле безопасности, если не выполняют функции, требуемые сертификатом; но если ИТ поддерживает, например, систему ПЛГ или EFB — нужен контроль через договор и аудит.

### Gaps
- Нет найденного первоисточника EASA/ФАВТ, прямо разрешающего одному лицу быть AM нескольких юрлиц группы или одну функцию CM на несколько сертификатов — требует отдельной проверки (GM к ORO.GEN.200/CAMO.A.200/145.A.200).
