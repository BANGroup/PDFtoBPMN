# Референтные модели процессов, кроме APQC, для архитектуры процессов авиагруппы (авиакомпания, вертолётный оператор, ТОиР/MRO, ИТ-дочка)

Дата сбора: 2026-10-03. Факты с URL отделены от выводов. Названия моделей и стандартов даны в оригинале.

## 1. ISO 9001 (process approach, п. 4.4), Annex SL / Harmonized Structure, ИСМ, классификация «управление / основные / обеспечивающие», статус ревизии 2026

### Takeaway
ISO 9001 не задаёт готовой карты процессов. Он требует определить процессы СМК, их входы и выходы, последовательность и взаимодействие, критерии, ресурсы, ответственность и риски (п. 4.4). Деление на «управляющие / основные / обеспечивающие» процессы взято из практики, в тексте стандарта его нет. Harmonized Structure (п. 4–10) позволяет вести одну ИСМ по ISO 9001, 14001 и 45001. ISO 9001:2026 (шестое издание) утверждён на стадии FDIS 7 августа 2026 года; по нескольким источникам, он опубликован 16 сентября 2026 года.

### Cited Findings
- П. 4.4 требует: определить процессы, нужные СМК, и их применение; определить входы и ожидаемые выходы; последовательность и взаимодействие; критерии и методы, включая мониторинг, измерения и показатели; ресурсы; ответственность и полномочия; риски и возможности по 6.1; оценивать и изменять процессы; улучшать процессы и СМК — [Auditor Training Online](https://blog.auditortrainingonline.com/blog/explaining-iso-9001-clause-4.4-quality-management-system-part-one); [Presencis, ст. 4.4](https://cdn.presencis.com/regulations/iso-9001/article-4.4/)
- Process approach — один из семи принципов менеджмента качества, на которых построен ISO 9001. Для описания процессов и аудита на практике применяют SIPOC и turtle diagram — [Open Exam Prep](https://open-exam-prep.com/study-guides/iso-9001-lead-auditor/chapter-1/process-approach-risk-pdca); [PECB, Process approach](https://pecb.com/en/article/process-approach)
- ISO 9001, 14001 и 45001 построены по Annex SL, Appendix 2 к ISO/IEC Directives. Редакция 2021 года вышла в мае 2021 и применяется ко всем новым и пересматриваемым стандартам систем менеджмента — [IAF news, 2021](https://iaf.news/2021/07/02/new-2021-edition-of-annex-sl-for-management-system-standards/)
- Общая структура разделов: Scope, Normative references, Terms and definitions, Context of the organization, Leadership, Planning, Support, Operation, Performance evaluation, Improvement. Тексты разделов 4, 5, 7, 9 и 10 почти совпадают во всех стандартах, специфика сосредоточена в разделах 6 и 8 — [Advisera](https://advisera.com/articles/how-to-implement-integrated-management-systems/)
- Статус ISO 9001:2026. DIS разослан членам ISO 27 августа 2025 года ([NSAI, Dec 2025](https://www.nsai.ie/images/uploads/general/ISO_9001_Revision_information_-_Dec_25.pdf); [DQS](https://www.dqsglobal.com/en/learn/blog/revision-iso-9001)). FDIS утверждён «with overwhelming international support»; шестое издание «scheduled for publication on 16 September 2026» — [ISO/TC 176/SC 2 news](https://committee.iso.org/sites/tc176sc2/home/news/content-left-area/news-and-updates/news-1.html). Дату утверждения FDIS 7 августа 2026 года называет [CBQA Global](https://cbqaglobal.com/blog/2026/09/09/iso-fdis-9001-approved-what-does-it-mean-for-iso-90012026-transition/)
- Расхождение. Сторонние источники пишут, что стандарт опубликован 16.09.2026 и заменяет ISO 9001:2015 вместе с Amd 1:2024 (climate change) ([qms2go](https://qms2go.com/iso-9001-2026); [Effivity](https://www.effivity.com/blog/iso-9001-2026-changes)). При этом на [iso.org/standard/9001](https://www.iso.org/standard/9001) в выдаче поиска фигурирует «Final Draft». Факт публикации по первичному источнику ISO 3 октября 2026 года не подтверждён.
- Переход: сертификаты ISO 9001:2015 нужно перевести до 30.09.2029 (трёхлетний переходный период, Global Accreditation Cooperation) — [qms2go](https://qms2go.com/iso-9001-2026). Срок около трёх лет называет и [CBQA](https://cbqaglobal.com/blog/2026/09/09/iso-fdis-9001-approved-what-does-it-mean-for-iso-90012026-transition/)
- Основные изменения 2026: термины из Harmonised Structure и ISO 9000:2026; новые требования о quality culture и ethical behaviour; переработан п. 6.1, риски и возможности разведены чётче — [qms2go](https://qms2go.com/iso-9001-2026); [CQI Knowledge Hub](https://knowledge.quality.org/article/iso-90012026-revision-guidance)
- ГОСТ Р ИСО 9001-2015 — российская идентичная версия ISO 9001:2015. Это известный факт, но в этой сессии карточка стандарта не открывалась, поэтому он перенесён в Gaps.

### Inferences
- П. 4.4 задаёт требования к атрибутам процесса в карте (владелец, входы и выходы, показатели, ресурсы, риски, связи), но не к её уровням. Уровни 1 и 2 можно строить по любой референтной модели (APQC, отраслевой цепочке ценности), если у каждого процесса есть эти атрибуты.
- Тройка «управляющие / основные (бизнес) / обеспечивающие» — общепринятая практическая конвенция, в тексте ISO её нет. Её удобно использовать как группировку уровня 0 над процессами уровня 1.
- В авиагруппе к СМК добавляются СУБП (SMS), ISO 14001, ISO 45001 и, возможно, ISO/IEC 27001. Harmonized Structure позволяет вести общие процессы «руководство, планирование, поддержка, оценка, улучшение» один раз, а специфику раздела 8 Operation раскладывать по основным процессам. Это аргумент вынести «управление системами менеджмента / ИСМ» в один процесс уровня 1 в блоке управления.
- После выхода ISO 9001:2026 требования п. 4.4 по существу, по-видимому, не меняются: в списках изменений его нет. Это стоит проверить по тексту стандарта.

### Gaps
- Полный текст ISO 9001:2026, п. 4.4, не прочитан. Сравнение с 2015 сделано только по вторичным источникам.
- Не выяснено, утверждён ли ГОСТ Р ИСО 9001-2026 или есть ли проект идентичного ГОСТ Р.
- Первичная страница ISO о факте публикации (а не о плановой дате) не получена.

## 2. SCOR Digital Standard (ASCM): верхний уровень и применимость к ТОиР и снабжению запчастями

### Takeaway
В SCOR DS семь процессов верхнего уровня: Orchestrate, Plan, Order, Source, Transform, Fulfill, Return. Прежние Make, Deliver и Enable заменены на Transform, Order/Fulfill и Orchestrate. В Transform прямо названы maintenance, repair and overhaul, поэтому SCOR DS подходит для детализации уровня 2+ в ТОиР, логистике и снабжении авиазапчастями (ротабельный фонд, ремонтный цикл агрегатов, возвраты).

### Cited Findings
- SCOR DS включает семь primary management processes: Orchestrate, Plan, Order, Source, Transform, Fulfill, Return — [ASCM SCOR DS](https://www.ascm.org/corporate-solutions/standards-tools/scor-ds/); [ASCM Northern New England](https://northernnewengland.ascm.org/SCOR)
- Orchestrate охватывает интеграцию и обеспечение стратегий цепи поставок: бизнес-правила, планирование, HR, сеть и технологии, аналитику данных, контракты, регуляторику и compliance, риски, ESG, circular supply chain, управление результативностью — [ASCM SCOR DS](https://www.ascm.org/corporate-solutions/standards-tools/scor-ds/)
- Transform включает «production; assembly and disassembly; maintenance, repair and overhaul». Return описывает обратный поток товаров и услуг: диагностику состояния, проверку прав (entitlement) и диспозицию обратно в Transform или в другие циклические операции — [ASCM SCOR DS](https://www.ascm.org/corporate-solutions/standards-tools/scor-ds/)
- Order — работа с заказом клиента (цены, оплата, статус). Fulfill — исполнение заказов и услуг: доставка, комплектация, отгрузка, установка, ввод в эксплуатацию, выставление счетов. Source — закупка, график поставок, приёмка, передача — [ASCM SCOR DS](https://www.ascm.org/corporate-solutions/standards-tools/scor-ds/)

### Inferences
- Для MRO-дочки и службы материально-технического обеспечения авиакомпании SCOR DS удобен на уровнях 2–3. Plan даёт планирование потребности в запчастях и ремонтах. Source даёт закупки и пул-соглашения. Transform даёт ремонт агрегатов и двигателей (MRO). Fulfill даёт выдачу на борт и AOG-поставки. Return даёт снятые компоненты и цикл ремонта ротабельных агрегатов (repair loop).
- Orchestrate пересекается с корпоративными функциями (HR, ИТ, риски). В групповой архитектуре его лучше не дублировать на уровне 1, а связать с соответствующими процессами блоков управления и обеспечения.
- SCOR DS поставляет и метрики (уровни reliability, responsiveness, agility, cost, assets в классической SCOR), их можно использовать как показатели процессов для п. 4.4. Перечень метрик именно в SCOR DS в этой сессии не проверялся.

### Gaps
- Не проверены декомпозиция SCOR DS уровней 2–3 (коды и названия) и условия доступа к ней (членство ASCM).
- Отраслевых кейсов применения SCOR в авиационном MRO из первичных источников не найдено.

## 3. ITIL 4 / ITIL (Version 5) и COBIT 2019 для ИТ-дочки

### Takeaway
В ITIL 4 34 practices: 14 general, 17 service и 3 technical management. В январе 2026 года PeopleCert анонсировал ITIL (Version 5) с теми же 34 практиками, ориентированный на digital product and service management и AI. ITIL 4 пока действует параллельно. В COBIT 2019 40 governance/management objectives в пяти доменах: EDM 5, APO 14, BAI 11, DSS 6, MEA 4. Уровни 2–3 процессов ИТ-дочки можно строить по COBIT (рамка «управление + менеджмент») и детализировать по практикам ITIL.

### Cited Findings
- В ITIL 4 34 практики в трёх группах: 14 general, 17 service и 3 technical management practices. В ITIL v3 они назывались processes — [IONOS](https://www.ionos.com/digitalguide/online-marketing/online-sales/what-is-itil-v4/); [ITSM.tools, полный список](https://itsm.tools/34-itil-4-management-practices/)
- ITIL (Version 5) анонсирован PeopleCert в январе 2026 года как best practice framework for digital product and service management. В нём 34 практики, полный доступ к ним через PeopleCert Plus. В 2026 году внедряется поэтапно, ITIL 4 действует параллельно — [ITIL, Wikipedia](https://en.wikipedia.org/wiki/ITIL); [Advised Skills](https://www.advisedskills.com/blog/it-service-management/itil-version-5-in-2026-what-is-confirmed-what-is-available-and-what-comes-next.md); [Global Knowledge FAQ](https://www.globalknowledge.com/en/certifications/certification-training/itil/itil-version-5-certification-faq)
- В COBIT 2019 40 objectives в пяти доменах. EDM (Evaluate, Direct and Monitor) — governance. APO (Align, Plan and Organize), BAI (Build, Acquire and Implement), DSS (Deliver, Service and Support), MEA (Monitor, Evaluate and Assess) — management. Число objectives: EDM 5, APO 14, BAI 11, DSS 6, MEA 4 — [ISACA news, 2018](https://www.isaca.org/resources/news-and-trends/industry-news/2018/a-new-cobit-is-in-town-and-i-really-like-how-it-looks); [Open Exam Prep](https://open-exam-prep.com/study-guides/cobit-2019/core-model-and-edm/forty-objectives-core-model)

### Inferences
- Для ИТ-дочки авиагруппы домены COBIT могут стать уровнем 2 процесса «Управление ИТ». EDM ложится в корпоративное управление группой, APO — в стратегию и архитектуру, BAI — в разработку и внедрение, DSS — в эксплуатацию, MEA — в контроль. Практики ITIL (Incident, Change, Service desk и др.) — уровень 3 внутри DSS и BAI.
- Если ИТ-дочка оказывает услуги другим компаниям группы, её «основные» процессы (выпуск и поддержка ИТ-сервисов) в архитектуре группы становятся «обеспечивающими». Стык удобно описывать через каталог сервисов и SLA (APO09 Managed Service Agreements в COBIT; Service level management в ITIL).
- Список практик ITIL 5 может отличаться от ITIL 4 названиями. Перед фиксацией в модели нужна сверка.

### Gaps
- Сравнение 34 практик ITIL 5 с ITIL 4 по названиям не выполнено: материалы закрыты (PeopleCert Plus).
- Не выяснено, выходил ли в 2025–2026 годах COBIT новее 2019.

## 4. eTOM (TM Forum Business Process Framework) как структурная аналогия отраслевой модели уровней 0/1

### Takeaway
eTOM — пример отраслевой (телеком) референтной модели. На уровне 0 в ней три вертикальные области: Strategy, Infrastructure & Product (SIP), Operations, Enterprise Management. Их пересекают горизонтальные функциональные группы (рынок/продукт/клиент, сервис, ресурс, поставщик/партнёр). Для авиагруппы ценна не сама модель, а её матричный принцип «жизненный цикл × объект управления».

### Cited Findings
- Business Process Framework — название eTOM (enhanced Telecom Operations Map) в TM Forum с 2013 года. Уровень 0 — три области: Strategy, Infrastructure and Product (планирование и управление жизненным циклом), Operations («ядро» операционного управления), Enterprise Management (корпоративные и обеспечивающие процессы) — [CIO Wiki, eTOM](https://cio-wiki.com/wiki/ETOM); [TM Forum, Myths around eTOM](https://tmforum.org/press-and-news/myths-around-etom)
- SIP разрабатывает стратегии, планирует и развивает инфраструктуру и продукты, управляет цепью поставок. Operations включает ежедневную операционную поддержку и процессы готовности (readiness). Enterprise Management содержит базовые процессы управления любой крупной организацией — [CIO Wiki](https://cio-wiki.com/wiki/ETOM)
- Горизонтальные функциональные группы: Market, Product & Customer; Service; Resource (Application, Computing and Network); Supplier/Partner — [CIO Wiki](https://cio-wiki.com/wiki/ETOM)

### Inferences
- Аналогия для авиагруппы. «Strategy, Infrastructure & Product» соответствует развитию сети маршрутов, флота, продукта и инфраструктуры. «Operations» — производственному циклу (продажи → планирование рейсов → выполнение полётов → ТО → обслуживание пассажиров и грузов). «Enterprise Management» — корпоративным функциям. Горизонтали можно перенести так: клиент/рынок; продукт/рейс; ресурсы (ВС, экипажи, инфраструктура); поставщики и партнёры (аэропорты, MRO, альянсы).
- Разделение «Operations vs Readiness» (operations support and readiness) полезно для авиации: процессы поддержания готовности (лётная годность, допуски персонала) стоит отделять от выполнения рейса.

### Gaps
- Актуальная версия Business Process Framework (номер релиза на 2026 год) и её связь с TM Forum ODA не проверены: страницы TM Forum с моделью требуют входа.

## 5. Авиационные отраслевые референсы: IATA AIDM, ATA Spec 2000, iSpec 2200, MRO-модели, вертолётные операторы, «airline value chain»

### Takeaway
Отраслевые авиастандарты — это прежде всего модели данных и обмена сообщениями: AIDM — пассажирский и коммерческий домен, Spec 2000 — материалы, ремонты и надёжность. Модели процессов уровней 0–1 они не задают, но полезны как словари объектов и бизнес-событий на уровнях 2–4. Опубликованной общепризнанной референтной модели процессов авиакомпании, MRO или вертолётного оператора, сопоставимой с eTOM, в этой сессии не найдено.

### Cited Findings
- IATA AIDM (Airline Industry Data Model) — интегрированная логическая модель данных (I3), сгруппированная по 26 subject areas. Среди доменов: Flights, Parties, Shopping, Order Management, Payments, Aircraft Configuration, Baggage и другие — [IATA Developer, About AIDM](https://developer.iata.org/en/aidm/); [IATA AIDM Confluence](https://standards.atlassian.net/wiki/spaces/AIDM); [IATA Industry Data Model](https://www.iata.org/en/about/corporate-structure/passenger-standards-conference/architecture-technology-strategy/industry-data-model/)
- ATA Spec 2000 — глобальная спецификация для автоматизации бизнес-процессов и обмена информацией по запчастям, материалам, ТО и надёжности. Области: Provisioning, Spares and Procurement Planning, Purchase Order Administration and Invoicing, Repair Order Administration, Reliability Data Exchange, Delivery Configuration, Warranty Processing, Parts Tracking/Traceability (barcode, 2D data matrix, RFID), Industry Performance Metrics, Regulatory Documentation, Electronic Logbook — [A4A, ATA e-Business Program](https://showcase.airlines.org/ata-e-business-program/)
- Отдельные главы Spec 2000: Ch 2 Procurement Planning, Ch 8 Repair Database, Ch 11 Reliability Data Collection/Exchange (ред. 2023.1, есть XML Schema), Ch 12 Surplus Database, Ch 13 Industry Metrics — [A4A Publications, Ch 11](https://publications.airlines.org/products/spec-2000-reliability-data-collection-exchange-ch-11-revision-2023-1); [Ch 2](https://publications.airlines.org/products/spec-2000-procurement-planning-ch-2-revision-2014-1); [Ch 13](https://publications.airlines.org/products/spec-2000-industry-metrics-ch-13-revision-2014-1)

### Inferences
- AIDM полезен для коммерческого блока (продажи, NDC/ONE Order, обслуживание пассажиров и багажа) на уровнях 2–3: subject areas подсказывают объекты процессов и границы между ними (Order Management, Payments).
- Главы Spec 2000 почти один к одному ложатся на процессы уровня 2–3 блока «Поддержание лётной годности и ТОиР / МТО»: планирование закупок, заказы на ремонт, гарантия, прослеживаемость, надёжность, метрики. Вместе с SCOR DS это готовый каркас для MRO и снабжения.
- Регуляторный «каркас» процессов авиакомпании и вертолётного оператора на практике задают требования к сертификату эксплуатанта и СУБП: ICAO Annex 6 и 19, ФАП. Это вывод, первичные источники в этой сессии не проверялись.

### Gaps
- Структура ATA iSpec 2200 (стандарт технической документации ВС, ATA chapters) в этой сессии по первичному источнику не проверена. Spec 2500 не найден, такого стандарта, возможно, нет.
- Публичной референтной модели процессов MRO (кроме SCOR DS и Spec 2000) и модели процессов вертолётного оператора не найдено.
- Отдельной опубликованной «airline value chain» модели IATA или другого авторитетного источника не найдено.

## 6. Цепочка ценности Портера и её адаптация для авиакомпании

### Takeaway
Классическая цепочка ценности Портера (1985) делит деятельность на 5 первичных и 4 вспомогательных видов. Для авиакомпании первичные виды приходится переименовывать под сервисный характер бизнеса. Авторитетной первичной «авиационной» адаптации не найдено, поэтому соответствие ниже — вывод.

### Cited Findings
- Первичные виды деятельности: Inbound Logistics, Operations, Outbound Logistics, Marketing & Sales, Service. Вспомогательные: Firm Infrastructure, Human Resource Management, Technology Development, Procurement. Модель предложена M. Porter в 1985 году — [LibreTexts, The Value Chain](https://eng.libretexts.org/Courses/Delta_College/Master_CS11_POCR/02:_Technology_Enabled_Strategy/2.06:_The_Value_Chain); [Wrike](https://wrike.com/blog/porters-value-chain)
- Примеры разбора цепочки ценности авиакомпаний есть только в непервичных публикациях (например, British Airways) — [ePlaneAI](https://www.eplaneai.com/zh/news/analysis-of-british-airways-value-chain). Качество источника низкое.

### Inferences
- Возможное соответствие для авиакомпании. Inbound logistics — обеспечение ресурсами (флот, топливо, слоты, наземное обслуживание). Operations — планирование и выполнение полётов, ТО. Outbound logistics — обслуживание пассажиров, багажа и груза в аэропорту. Marketing & Sales — сеть, ценообразование, продажи, дистрибуция. Service — лояльность, работа с претензиями.
- Для группы цепочку Портера лучше применять на уровне 0, отдельно для каждой бизнес-линии: авиаперевозки, вертолётные работы, MRO, ИТ-услуги. Во «вспомогательной» части она согласуется с блоками «управление / обеспечение» по ISO-практике.

### Gaps
- Не найдено академического или отраслевого первичного источника с канонической адаптацией цепочки ценности Портера к авиакомпании или вертолётному оператору.

## 7. Российские стандарты и Business Studio

### Takeaway
Российского национального стандарта, который задавал бы архитектуру процессов предприятия, не найдено. ГОСТ Р 57193 описывает процессы жизненного цикла систем (по ISO/IEC/IEEE 15288), а не процессы организации; редакция 2016 года заменена ГОСТ Р 57193-2025. Business Studio публикует типовые модели верхнего уровня для производства, энергетики, строительства и розницы; авиационной модели в открытом перечне нет.

### Cited Findings
- ГОСТ Р 57193-2016 «Системная и программная инженерия. Процессы жизненного цикла систем» основан на ISO/IEC/IEEE 15288:2015. Действовал с 01.11.2017, заменил ГОСТ Р ИСО/МЭК 15288-2005, сам заменён ГОСТ Р 57193-2025 — [Гостинфо](https://cn.gostinfo.ru/catalog/Details/?id=6260370); [Meganorm](https://meganorm.ru/mega_doc/norm/gost-r_gosudarstvennyj-standart/14/gost_r_57193-2016_natsionalnyy_standart_rossiyskoy.html)
- Процессы стандарта применимы на любом уровне иерархии системы и на протяжении всего жизненного цикла — [Meganorm](https://meganorm.ru/mega_doc/norm/gost-r_gosudarstvennyj-standart/14/gost_r_57193-2016_natsionalnyy_standart_rossiyskoy.html)
- Типовые модели на businessstudio.ru: «Модель процессов верхнего уровня производственной компании», «Модель процессов верхнего уровня энергетической компании (генерация)», «Модель деятельности производственного предприятия (дискретное производство)», «Процессная модель строительной генподрядной организации», «Типовая модель „Управление торговой сетью“», а также «Сборники стратегий и бизнес-процессов организаций (со спецификой каждой отрасли)». Модели авиакомпании или ТОиР в перечне нет — [Business Studio, типовые модели](https://www.businessstudio.ru/procedures/business/model/)

### Inferences
- ГОСТ Р 57193 (15288) пригоден как референс для процессов жизненного цикла технических систем: ИТ-систем в ИТ-дочке, модификаций ВС и оборудования. Как модель уровня 1 для всей группы он не подходит.
- Для авиагруппы в Business Studio, вероятно, придётся собирать модель самим: верхний уровень по ISO-группировке и цепочке ценности, детализация по SCOR DS, Spec 2000, COBIT/ITIL и AIDM. Типовую модель производственной компании можно взять как шаблон оформления, но не содержания.

### Gaps
- Текст и состав процессов ГОСТ Р 57193-2025 не проверены.
- Не проверено, есть ли в платных «Сборниках» Business Studio транспортная или авиационная отрасль.
- Специальный российский стандарт архитектуры бизнес-процессов не найден. Возможные кандидаты (серии по ИСМ, ГОСТ Р ИСО 9004) не проверены.
