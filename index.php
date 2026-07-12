<?php
error_reporting(E_ALL);
ini_set('display_errors', 1);

$host = "localhost";
$user = "root";
$pass = "sunfra";
$db   = "auto_batching";

$conn = new mysqli($host, $user, $pass, $db);
if ($conn->connect_error) {
    die("Database connection failed: " . $conn->connect_error);
}

$selectedDate = isset($_GET['date']) ? $_GET['date'] : date('Y-m-d');

$apiUrl = "http://localhost:8080/php/shead_chick_grower_json.php";
$response = @file_get_contents($apiUrl);
$sheadData = json_decode($response, true);

$sheadNames = [];
if (!empty($sheadData)) {
    foreach ($sheadData as $item) {
        if (isset($item['shead_name'])) {
            $sheadNames[] = $item['shead_name'];
        }
    }
}

$sheadCounts = [];
if (!empty($sheadNames)) {
    $placeholders = implode(',', array_fill(0, count($sheadNames), '?'));
    $sql = "SELECT shead_name, COUNT(*) AS count_value 
            FROM batching_running_logs 
            WHERE DATE(date) = ? AND shead_name IN ($placeholders)
            GROUP BY shead_name
            ORDER BY shead_name";

    $stmt = $conn->prepare($sql);
    $types = str_repeat('s', count($sheadNames) + 1);
    $params = array_merge([$selectedDate], $sheadNames);
    $stmt->bind_param($types, ...$params);
    $stmt->execute();
    $result = $stmt->get_result();

    foreach ($sheadNames as $name) {
        $sheadCounts[$name] = 0;
    }
    while ($row = $result->fetch_assoc()) {
        $sheadCounts[$row['shead_name']] = (int)$row['count_value'];
    }
    $stmt->close();
}

$feedSql = "SELECT * FROM feed_rawmaterial ORDER BY type, name";
$feedResult = $conn->query($feedSql);

$rawMaterials = [];
$feedMedicines = [];

if ($feedResult && $feedResult->num_rows > 0) {
    while ($row = $feedResult->fetch_assoc()) {
        if (trim(strtolower($row['type'])) == 'raw material') {
            $rawMaterials[] = $row;
        } else {
            $feedMedicines[] = $row;
        }
    }
}

$conn->close();
?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Grinding & Stock Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
body {
    margin: 0;
    font-family: 'Segoe UI', sans-serif;
    background: linear-gradient(120deg, #ADD8E6, #ADD8E6);
}

/* Sidebar */
.sidebar {
  width: 180px;
  background-color: #2c3e50;
  color: #fff;
  display: flex;
  flex-direction: column;
  padding-top: 15px;
  position: fixed;
  left: 0; top: 0; bottom: 0;
  box-shadow: 2px 0 10px rgba(0,0,0,0.2);
}
.sidebar h2 {
  text-align: center;
  margin-bottom: 20px;
  font-size: 16px;
  color: #ecf0f1;
}
.sidebar a {
  padding: 8px 12px;
  text-decoration: none;
  color: #ecf0f1;
  font-size: 13px;
  transition: all 0.3s;
}
.sidebar a:hover {
  background-color: #34495e;
  padding-left: 20px;
}


/* Main content */
.main-content {
    margin-left: 180px;
    padding: 25px;
}
h1 {
    color: #1b263b;
    font-size: 28px;
    margin-bottom: 15px;
}
.date-form {
    display: flex;
    gap: 10px;
    align-items: center;
    margin-bottom: 20px;
}
.date-form input {
    padding: 8px 12px;
    font-size: 16px;
    border-radius: 6px;
    border: 1px solid #ccc;
}

/* Chart */
.chart-card {
    background: rgba(255,255,255,0.8);
    backdrop-filter: blur(10px);
    padding: 15px 25px;
    border-radius: 15px;
    box-shadow: 0 8px 16px rgba(0,0,0,0.1);
    margin-bottom: 30px;
}
.chart-card h3 {
    text-align: center;
    color: #2e86de;
    margin-bottom: 10px;
}
canvas {
    width: 100% !important;
    height: 180px !important; /* small graph */
}

/* Section headers */
.section-title {
    font-size: 22px;
    margin: 25px 0 15px;
    color: #1b263b;
    text-align: center;
    position: relative;
}
.section-title::after {
    content: '';
    position: absolute;
    left: 50%;
    bottom: -5px;
    width: 60px;
    height: 3px;
    background: #2e86de;
    transform: translateX(-50%);
    border-radius: 5px;
}

/* Feed grids */
.feed-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
    gap: 18px;
}
.feed-card {
    background: #fff;
    border-radius: 15px;
    padding: 18px 20px;
    box-shadow: 0 3px 12px rgba(0,0,0,0.1);
    transition: transform 0.3s;
}
.feed-card:hover {
    transform: translateY(-5px);
}
.feed-card h4 {
    margin: 0;
    font-size: 18px;
    color: #1b263b;
}
.feed-card p {
    margin: 5px 0;
    font-size: 16px;
    color: #333;
}
.feed-card small {
    color: #7f8c8d;
    font-size: 13px;
}
.progress {
    height: 7px;
    background: #edf2f7;
    border-radius: 5px;
    margin-top: 10px;
    overflow: hidden;
}
.progress-bar {
    height: 100%;
    border-radius: 5px;
    transition: width 0.6s ease;
}

/* Raw Material */
.raw .feed-card { border-left: 8px solid #2980b9; }
/* Feed Medicine */
.medicine .feed-card { border-left: 8px solid #e67e22; }
.section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: 25px;
    margin-bottom: 10px;
}

.section-header input {
    padding: 8px 12px;
    border-radius: 8px;
    border: 1px solid #ccc;
    font-size: 15px;
    width: 240px;
    outline: none;
    transition: all 0.3s;
}
.section-header input:focus {
    border-color: #2e86de;
    box-shadow: 0 0 5px rgba(46, 134, 222, 0.5);
}.sync-container {
    position: absolute;
    top: 20px;
    right: 30px;
}

#syncBtn {
    background-color: #2e86de;
    color: white;
    border: none;
    border-radius: 8px;
    padding: 10px 20px;
    font-size: 15px;
    cursor: pointer;
    box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    transition: all 0.3s ease;
}

#syncBtn:hover {
    background-color: #1b4f72;
    transform: scale(1.05);
}


</style>
</head>
<body>

<div class="sidebar">
    <h2>Dashboard</h2>
    <a href="index.php">🏠 Home</a>
    <a href="shead_config.php">⚙️ Configuration</a>
    <a href="feed_formula_json_to_web.php">📊 Feed Formula</a>
    <a href="report.php">📊 Report</a>
    <a href="https://sunfra.com/">💬 Support</a>
</div>

<div class="main-content">
    <h1>Grinding & Stock Dashboard</h1>
    <div class="sync-container">
        <button id="syncBtn">🔄 Sync</button>
    </div>

    <div class="date-form">
        <label for="date">Select Date:</label>
        <input type="date" id="date" value="<?php echo $selectedDate; ?>">
    </div>

    <div class="chart-card">
        <h3>Grinding Count Overview</h3>
        <canvas id="sheadChart"></canvas>
    </div>

    <div class="section-header">
        <h2 class="section-title">Raw Material</h2>
        <input type="text" id="rawSearch" placeholder="🔍 Search Raw Material...">
    </div>

    <div class="feed-grid raw" id="rawGrid">
        <?php foreach ($rawMaterials as $mat): 
            $maxStock = 50000;
            $percent = min(100, ($mat['stock'] / $maxStock) * 100);
        ?>
        <div class="feed-card" data-name="<?php echo strtolower(htmlspecialchars($mat['name'])); ?>">
            <h4><?php echo htmlspecialchars($mat['name']); ?></h4>
            <p><strong><?php echo htmlspecialchars($mat['stock']); ?> <?php echo htmlspecialchars($mat['metrics']); ?></strong></p>
            <small><?php echo htmlspecialchars($mat['type']); ?></small>
            <div class="progress">
                <div class="progress-bar" style="width:<?php echo $percent; ?>%; background:#2980b9;"></div>
            </div>
        </div>
        <?php endforeach; ?>
    </div>

    <div class="section-header">
        <h2 class="section-title">Feed Medicine</h2>
        <input type="text" id="medicineSearch" placeholder="🔍 Search Feed Medicine...">
    </div>

    <div class="feed-grid medicine" id="medicineGrid">
        <?php foreach ($feedMedicines as $mat): 
            $maxStock = 10000;
            $percent = min(100, ($mat['stock'] / $maxStock) * 100);
        ?>
        <div class="feed-card" data-name="<?php echo strtolower(htmlspecialchars($mat['name'])); ?>">
            <h4><?php echo htmlspecialchars($mat['name']); ?></h4>
            <p><strong><?php echo htmlspecialchars($mat['stock']); ?> <?php echo htmlspecialchars($mat['metrics']); ?></strong></p>
            <small><?php echo htmlspecialchars($mat['type']); ?></small>
            <div class="progress">
                <div class="progress-bar" style="width:<?php echo $percent; ?>%; background:#e67e22;"></div>
            </div>
        </div>
        <?php endforeach; ?>
    </div>
</div>

<script>
document.getElementById('date').addEventListener('change', function() {
    const date = this.value;
    const url = new URL(window.location.href);
    url.searchParams.set('date', date);
    window.location.href = url.toString();
});

const ctx = document.getElementById('sheadChart').getContext('2d');
const data = <?php echo json_encode($sheadCounts); ?>;
new Chart(ctx, {
    type: 'bar',
    data: {
        labels: Object.keys(data),
        datasets: [{
            label: 'Tons',
            data: Object.values(data),
            backgroundColor: '#2e86de',
            borderRadius: 6
        }]
    },
    options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
            y: { beginAtZero: true, grid: { color: '#ecf0f1' } },
            x: { ticks: { color: '#34495e' } }
        }
    }
});
function setupSearch(inputId, gridId) {
    const input = document.getElementById(inputId);
    const grid = document.getElementById(gridId);
    const cards = grid.querySelectorAll(".feed-card");

    input.addEventListener("input", () => {
        const query = input.value.toLowerCase();
        cards.forEach(card => {
            const name = card.dataset.name;
            card.style.display = name.includes(query) ? "block" : "none";
        });
    });
}

setupSearch("rawSearch", "rawGrid");
setupSearch("medicineSearch", "medicineGrid");

document.getElementById("syncBtn").addEventListener("click", () => {
    const btn = document.getElementById("syncBtn");
    btn.textContent = "⏳ Syncing...";
    btn.disabled = true;

    fetch("http://localhost:8080/php/sync.php")
        .then(response => response.text())
        .then(data => {
            alert("✅ Sync completed successfully!");
            console.log("Sync Response:", data);
        })
        .catch(error => {
            alert("❌ Sync failed. Check console for details.");
            console.error("Sync Error:", error);
        })
        .finally(() => {
            btn.textContent = "🔄 Sync";
            btn.disabled = false;
        });
});

</script>

</body>
</html>
