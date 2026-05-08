from dataclasses import dataclass


@dataclass
class Location:
    id: str
    name: str
    lat: float
    lon: float
    description: str
    expected_water_status: str
    category: str           # shrinkage | flooding | mixed
    baseline_date: str      # YYYY-MM-DD  reference "normal" period


LOCATIONS: list[Location] = [
    # ── Chronic shrinkage ────────────────────────────────────────────────────
    Location(
        id="lake_chad",
        name="Lake Chad",
        lat=12.95,
        lon=14.25,
        description=(
            "Lake Chad, West Africa. Once one of Africa's largest lakes, it has lost "
            "approximately 90% of its surface area since the 1960s due to agricultural "
            "water extraction, reduced rainfall, and population growth. Over 30 million "
            "people depend on it. Coordinate is at the southeastern shore of the southern "
            "pool, where open water, exposed mudflats, and irrigated agriculture all meet."
        ),
        expected_water_status="Lake should show open water in the southern basin. "
            "Significant shrinkage is expected versus 1970s baseline.",
        category="shrinkage",
        baseline_date="2000-01-01",
    ),
    Location(
        id="aral_sea",
        name="Aral Sea South Basin",
        lat=43.80,
        lon=59.10,
        description=(
            "Aral Sea Southern Basin, Uzbekistan/Kazakhstan. Once the world's fourth "
            "largest lake, diverted for Soviet cotton irrigation from the 1960s. The "
            "southern basin is nearly completely dry. Coordinate is at the Amu Darya "
            "delta wetland system where the last remaining water, exposed salt flat "
            "shoreline, and the surrounding arid landscape meet within a single 15km tile."
        ),
        expected_water_status="Minimal or no open water expected. Salt flats and "
            "exposed lakebed dominate. Any water present is a recovery signal.",
        category="shrinkage",
        baseline_date="2000-01-01",
    ),
    Location(
        id="lake_urmia",
        name="Lake Urmia",
        lat=37.60,
        lon=46.00,
        description=(
            "Lake Urmia, northwestern Iran. A hypersaline lake that has lost approximately "
            "80% of its volume since the 1970s due to upstream dam construction and "
            "agricultural water diversion. Coordinate is at the southeastern shore where "
            "pink halophyte salt flats, open hypersaline water, and irrigated wheat fields "
            "are all visible within the 15km tile."
        ),
        expected_water_status="Significantly reduced water extent. Salt flats and pink/red "
            "halophyte vegetation visible at margins. Some seasonal variation.",
        category="shrinkage",
        baseline_date="2000-01-01",
    ),
    Location(
        id="dead_sea",
        name="Dead Sea",
        lat=31.80,
        lon=35.55,
        description=(
            "Dead Sea, Jordan/Israel/Palestine. The lowest point on Earth, dropping "
            "approximately 1 metre per year due to water diversion from the Jordan River "
            "and mineral extraction industries. Coordinate is at the northern Dead Sea "
            "where the hypersaline lake, the receding shoreline with exposed salt flat, "
            "the Jordan River delta, and Israeli/Jordanian agricultural fields (dates, "
            "vegetables) are all captured within the 15km tile."
        ),
        expected_water_status="Deep blue hypersaline water, but shoreline clearly receding. "
            "White salt flats visible on exposed former lakebed.",
        category="shrinkage",
        baseline_date="2000-01-01",
    ),
    Location(
        id="salton_sea",
        name="Salton Sea",
        lat=33.05,
        lon=-115.70,
        description=(
            "Salton Sea, California, USA. California's largest lake by surface area, "
            "fed almost entirely by agricultural runoff from Imperial Valley. Shrinking "
            "rapidly as irrigation efficiency reduces inflow. Coordinate is at the "
            "southeastern shore where the receding saline lake, exposed white salt playa, "
            "and intensive Imperial Valley agriculture (alfalfa, vegetables) are all "
            "visible in the same 15km tile."
        ),
        expected_water_status="Shallow saline lake with clearly exposed salt/playa flats "
            "around the perimeter. Agricultural fields dominate the buffer zone.",
        category="shrinkage",
        baseline_date="2000-01-01",
    ),

    # ── Flooding / extreme seasonal variation ────────────────────────────────
    Location(
        id="lake_victoria",
        name="Lake Victoria",
        lat=0.05,
        lon=34.20,
        description=(
            "Lake Victoria, East Africa (Uganda/Kenya/Tanzania). Africa's largest lake "
            "by area. Experienced historic flooding in 2020 when water levels rose over "
            "1.2m above normal, inundating lakeshore communities. Coordinate is on the "
            "Kenyan northwestern shore near Kisumu, where the lake margin, inundated "
            "wetlands, and smallholder maize/sorghum farms are all within 15km."
        ),
        expected_water_status="Large open water body. Shoreline variation between flood "
            "and recession seasons is significant. Watch for inundated margin vegetation.",
        category="flooding",
        baseline_date="2018-01-01",
    ),
    Location(
        id="tonle_sap",
        name="Tonle Sap",
        lat=13.05,
        lon=103.85,
        description=(
            "Tonle Sap Lake, Cambodia. Southeast Asia's largest freshwater lake and a "
            "critical fishery. Undergoes extreme seasonal variation — expanding up to 3x "
            "in size during monsoon season. Coordinate is at the northern shore where "
            "the lake edge, flooded forest fringe, and surrounding rice paddies are all "
            "visible within the 15km tile."
        ),
        expected_water_status="Highly seasonal — large open water in Oct-Nov (flood peak), "
            "much smaller in April-May (dry season). Surrounded by flooded forest and rice.",
        category="flooding",
        baseline_date="2018-01-01",
    ),
    Location(
        id="okavango",
        name="Okavango Delta",
        lat=-19.80,
        lon=23.10,
        description=(
            "Okavango Delta, Botswana. UNESCO World Heritage site. An inland river delta "
            "that floods seasonally as Angolan rains arrive via the Okavango River. "
            "Coordinate is at the southeastern edge of the delta where the flood front, "
            "permanent channels, seasonal grassland, and cattle grazing land meet."
        ),
        expected_water_status="Seasonal flooding creates a mosaic of water channels and "
            "islands. Dry season shows grassland and scrub. Flood extent varies year to year.",
        category="flooding",
        baseline_date="2018-01-01",
    ),

    # ── Mixed / agricultural signal ──────────────────────────────────────────
    Location(
        id="po_valley",
        name="Lake Garda (Po Valley)",
        lat=45.55,
        lon=10.68,
        description=(
            "Lake Garda, northern Italy — the largest Italian lake and the primary "
            "freshwater reservoir for Po Valley irrigation. In the 2022 drought, Lake "
            "Garda dropped to historic lows, visibly exposing rock shelves and restricting "
            "water supply to surrounding agriculture. Coordinate is at the southern shore "
            "near Sirmione where the deep blue lake, the distinctive shoreline, and the "
            "surrounding Valpolicella vineyards and Po Valley crops are all visible within "
            "the 15km tile."
        ),
        expected_water_status="Mosaic of lagoon water, reed beds, and intensive agriculture. "
            "2022 drought visible as reduced lagoon extent and stressed crops.",
        category="mixed",
        baseline_date="2018-01-01",
    ),
    Location(
        id="mekong_delta",
        name="Mekong Delta",
        lat=10.05,
        lon=105.65,
        description=(
            "Mekong Delta, southern Vietnam. The rice bowl of Southeast Asia. Upstream "
            "dams in China and Laos have reduced seasonal flooding, reducing sediment "
            "delivery and freshwater flow. Coordinate is near Can Tho, the delta's "
            "largest city, where a dense network of canals, active rice paddies, and "
            "the Mekong main channel are all within the 15km tile."
        ),
        expected_water_status="Dense network of canals and rivers. Rice paddies in varying "
            "growth stages. Watch for flooded fields during wet season vs bare/dry in drought.",
        category="mixed",
        baseline_date="2018-01-01",
    ),
    Location(
        id="lake_turkana",
        name="Lake Turkana",
        lat=3.50,
        lon=36.05,
        description=(
            "Lake Turkana, Kenya/Ethiopia border. World's largest permanent desert lake. "
            "The Omo River provides 90% of its inflow. Since the Gibe III dam began "
            "operation in 2015, seasonal flooding has been eliminated and lake levels "
            "are declining. Coordinate is on the western shore where the green-tinted "
            "lake, rocky shoreline, and arid pastoral grazing land are all visible."
        ),
        expected_water_status="Large greenish-blue lake (algae give it a distinct colour). "
            "Level decline noticeable post-2015. Surrounding land is arid/semi-arid.",
        category="mixed",
        baseline_date="2018-01-01",
    ),
    Location(
        id="lake_titicaca",
        name="Lake Titicaca",
        lat=-15.85,
        lon=-70.02,
        description=(
            "Lake Titicaca, Peru/Bolivia border. World's highest navigable lake at 3,812m. "
            "Declining water levels driven by Andean glacier retreat reducing inflows and "
            "increased evaporation from warming temperatures. Coordinate is on the "
            "northwestern shore near Puno, where the deep blue lake, reed-covered margins, "
            "and quinoa/potato terraces on the altiplano are all within 15km."
        ),
        expected_water_status="Deep blue high-altitude lake. Clear water with visible depth. "
            "Level variations affect reed-covered margins. Surrounding altiplano is farmed.",
        category="mixed",
        baseline_date="2018-01-01",
    ),

    # ── River deltas ─────────────────────────────────────────────────────────
    Location(
        id="nile_delta",
        name="Nile Delta",
        lat=31.40,
        lon=30.40,
        description=(
            "Nile Delta, northern Egypt. One of the world's largest river deltas and "
            "Egypt's agricultural heartland. Since the Aswan High Dam (1970), sediment "
            "delivery has dropped 98%, causing coastal erosion and land subsidence. Rising "
            "Mediterranean sea levels and saltwater intrusion threaten farmland. Coordinate "
            "is on the Rosetta branch near the Mediterranean coast where the sinuous Nile "
            "channel, the delta headland, greenhouse farms, and dense agricultural patchwork "
            "are all visible within the 15km tile."
        ),
        expected_water_status="Dense network of irrigation canals between green crop fields. "
            "No large open water body — canals and field boundaries define the water signal. "
            "Coastal margin shows sea incursion.",
        category="mixed",
        baseline_date="2000-01-01",
    ),
    Location(
        id="tana_river",
        name="Tana River Delta",
        lat=-2.55,
        lon=40.52,
        description=(
            "Tana River Delta, coastal Kenya. Kenya's longest river meets the Indian Ocean "
            "through a mosaic of seasonally flooded grasslands, riverine forest, ox-bow "
            "lakes, and mangroves. The delta supports large-scale irrigation schemes (sugar "
            "cane, rice) that compete with seasonal flood pulses critical to the downstream "
            "ecosystem. Upstream dams and irrigation abstraction are reducing flood intensity. "
            "Coordinate is at the delta where the main river channel, flooded grassland, "
            "mangrove fringe, and agricultural blocks are all visible."
        ),
        expected_water_status="Braided river channels and ox-bow lakes visible year-round. "
            "Flood season (Apr-Jun, Oct-Nov) expands inundation across grasslands. "
            "Large-scale irrigated fields (sugar, rice) border the natural delta.",
        category="flooding",
        baseline_date="2018-01-01",
    ),
    Location(
        id="omo_river",
        name="Omo River Delta",
        lat=4.60,
        lon=36.15,
        description=(
            "Omo River Delta, Ethiopia/Kenya border — northern end of Lake Turkana. "
            "The Omo River provides over 90% of Lake Turkana's freshwater inflow via this "
            "delta. Since the Gibe III dam began operation in 2015, the annual flood pulse "
            "has been eliminated, the delta is contracting, and Lake Turkana levels are "
            "falling. Large-scale sugar-cane irrigation schemes now occupy former floodplain. "
            "Coordinate is at the delta fan where the brown alluvial channels spread into "
            "Lake Turkana's teal-green water, the shrinking delta lobe, and the bright-green "
            "sugar-cane plantation blocks are all visible."
        ),
        expected_water_status="Braided distributary channels fanning into Lake Turkana. "
            "Pre-2015: annual delta flooding and green floodplain. "
            "Post-2015: contracted delta, irrigated plantation replacing natural floodplain.",
        category="mixed",
        baseline_date="2018-01-01",
    ),
    Location(
        id="amazon_delta",
        name="Amazon Delta",
        lat=-0.80,
        lon=-50.20,
        description=(
            "Amazon River Delta (Marajó Island region), northern Brazil. The world's "
            "largest river by discharge empties into the Atlantic through a vast maze of "
            "channels, flooded forests (várzea), and wetlands around Marajó Island. The "
            "delta experiences extreme seasonal flooding — river stage varies up to 10m "
            "between wet and dry seasons. Smallholder agriculture and cattle ranching "
            "encroach on the várzea margins. Coordinate is at the eastern tip of Marajó "
            "Island where the main Amazon channel, flooded várzea forest, and agricultural "
            "clearings meet within the 15km tile."
        ),
        expected_water_status="Wide dark river channels year-round. Wet season (Feb-May) "
            "floods the surrounding várzea forest — the forest canopy appears submerged. "
            "Dry season exposes mudflats and island margins.",
        category="flooding",
        baseline_date="2018-01-01",
    ),
    Location(
        id="danube_delta",
        name="Danube Delta",
        lat=45.20,
        lon=29.40,
        description=(
            "Danube Delta, Romania/Ukraine — where the Danube meets the Black Sea. "
            "Europe's second largest and best-preserved delta, a UNESCO Biosphere Reserve. "
            "The delta supports reed beds, fish ponds, and seasonal floodplain agriculture. "
            "Upstream dams trap sediment, reducing delta growth. Coordinate is in the "
            "central Sfântu Gheorghe arm area where the main river channel, flooded reed "
            "beds, shallow lakes (lacuri), and agricultural polders are all visible within "
            "the 15km tile."
        ),
        expected_water_status="Mosaic of river channels, shallow open lakes, and reed beds. "
            "Spring flood (Apr-May) expands inundation. Agricultural polders on drained "
            "margins show crop patterns distinct from the natural delta.",
        category="flooding",
        baseline_date="2018-01-01",
    ),
    Location(
        id="mesopotamian_marshes",
        name="Mesopotamian Marshes",
        lat=30.90,
        lon=47.40,
        description=(
            "Mesopotamian Marshes, southern Iraq — confluence of the Tigris and Euphrates "
            "rivers. Once the world's third largest wetland and home to the Marsh Arabs for "
            "5,000 years, the marshes were 90% drained by Saddam Hussein in the 1990s. "
            "Partial re-flooding since 2003 has restored portions, but upstream dams in "
            "Turkey and Syria continue to reduce inflows, and salinity is rising. Coordinate "
            "is in the central marshes near Al-Hammar lake where open shallow water, reed "
            "bed islands, salt-encrusted dry marsh, and irrigated date palm plantations are "
            "all visible within the 15km tile."
        ),
        expected_water_status="Shallow open water with dense reed beds and exposed "
            "salt-encrusted mudflat. Recovery since 2003 is visible vs 1990s baseline. "
            "Water extent highly variable with upstream dam releases.",
        category="mixed",
        baseline_date="2000-01-01",
    ),
    Location(
        id="niger_delta",
        name="Niger Delta",
        lat=5.30,
        lon=5.30,
        description=(
            "Niger Delta, southern Nigeria — where the Niger River fans into the Gulf of "
            "Guinea through a maze of distributaries, mangrove swamps, and tidal creeks. "
            "The world's largest mangrove forest outside Southeast Asia. Decades of oil "
            "extraction have caused widespread pipeline spills, gas flaring, and mangrove "
            "die-off. Coordinate is in the central delta where active river channels, "
            "mangrove patches, degraded/cleared mangrove, and smallholder farm plots are "
            "all visible within the 15km tile."
        ),
        expected_water_status="Dark tidal creeks and distributary channels through dense "
            "green mangrove canopy. Oil spill areas visible as dark patches in mangrove. "
            "Cleared and degraded mangrove shows as bare or scrub land.",
        category="mixed",
        baseline_date="2000-01-01",
    ),
    Location(
        id="congo_delta",
        name="Lower Congo River",
        lat=-5.85,
        lon=13.05,
        description=(
            "Lower Congo River gorge, DRC — the final stretch of the Congo River before "
            "the Atlantic. The world's second largest river by discharge cuts through the "
            "Crystal Mountains in a dramatic gorge before reaching the sea. The lower Congo "
            "has the world's deepest river channel (over 220m). River discharge is relatively "
            "stable year-round due to the equatorial catchment. The area near Boma shows "
            "the dark wide river channel cutting through dense tropical rainforest, with "
            "smallholder agriculture on the valley margins. Cloud cover is frequent "
            "year-round due to the equatorial maritime climate."
        ),
        expected_water_status="Wide dark river channel cutting through dense green "
            "rainforest. River discharge stable — no strong seasonal variation. "
            "Cloud cover frequent; image_quality_limited expected for many months.",
        category="flooding",
        baseline_date="2018-01-01",
    ),
]

LOCATIONS_BY_ID: dict[str, Location] = {loc.id: loc for loc in LOCATIONS}
