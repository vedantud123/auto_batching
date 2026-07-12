<?php
error_reporting(E_ALL);
ini_set('display_errors', 1);

$host = "localhost";
$user = "root";
$pass = "sunfra";
$db   = "auto_batching";

$conn = new mysqli($host, $user, $pass, $db);
if ($conn->connect_error) {
    die("Connection failed: " . $conn->connect_error);
}

$apiUrl = "http://localhost:8080/php/shead_chick_grower_json.php";
$response = @file_get_contents($apiUrl);
$sheadData = json_decode($response, true);

$sheadNames = [];
if (!empty($sheadData)) {
    foreach ($sheadData as $shead) {
        $sheadNames[] = $shead['shead_name'];
    }
}

$filter = $_GET['filter'] ?? 'today';
$selectedShead = $_GET['shead'] ?? 'All';
$from_date = $_GET['from_date'] ?? null;
$to_date   = $_GET['to_date'] ?? null;

$condition = match($filter) {
    'yesterday' => "DATE(date) = CURDATE() - INTERVAL 1 DAY",
    'weekly'    => "YEARWEEK(date, 1) = YEARWEEK(CURDATE(), 1)",
    'monthly'   => "YEAR(date) = YEAR(CURDATE()) AND MONTH(date) = MONTH(CURDATE())",
    'yearly'    => "YEAR(date) = YEAR(CURDATE())",
    'custom'    => ($from_date && $to_date) ? "DATE(date) BETWEEN '".$conn->real_escape_string($from_date)."' AND '".$conn->real_escape_string($to_date)."'" : "1=1",
    default     => "DATE(date) = CURDATE()",
};

if ($selectedShead !== 'All') {
    $condition .= " AND shead_name = '".$conn->real_escape_string($selectedShead)."'";
}

$sql = "SELECT DATE(date) as log_date, shead_name, COUNT(*) as cnt 
        FROM batching_running_logs 
        WHERE $condition
        GROUP BY DATE(date), shead_name
        ORDER BY log_date DESC, shead_name ASC";
$result = $conn->query($sql);

$sheadDataArr = [];
if ($result && $result->num_rows > 0) {
    while ($row = $result->fetch_assoc()) {
        $sheadDataArr[$row['log_date']][$row['shead_name']] = $row['cnt'];
    }
}

$mat_condition = match($filter) {
    'yesterday' => "DATE(timestamp) = CURDATE() - INTERVAL 1 DAY",
    'weekly'    => "YEARWEEK(timestamp, 1) = YEARWEEK(CURDATE(), 1)",
    'monthly'   => "YEAR(timestamp) = YEAR(CURDATE()) AND MONTH(timestamp) = MONTH(CURDATE())",
    'yearly'    => "YEAR(timestamp) = YEAR(CURDATE())",
    'custom'    => ($from_date && $to_date) ? "DATE(timestamp) BETWEEN '".$conn->real_escape_string($from_date)."' AND '".$conn->real_escape_string($to_date)."'" : "1=1",
    default     => "DATE(timestamp) = CURDATE()",
};

$materials = [];
$res_mat = $conn->query("SELECT DISTINCT material_name FROM feed_material_reduction_logs ORDER BY material_name");
while($row = $res_mat->fetch_assoc()) {
    $materials[] = $row['material_name'];
}

$sql_mat = "SELECT DATE(timestamp) as log_date, material_name, SUM(reduced_quantity) as total_qty
            FROM feed_material_reduction_logs
            WHERE $mat_condition
            GROUP BY DATE(timestamp), material_name
            ORDER BY log_date DESC, material_name ASC";
$result_mat = $conn->query($sql_mat);

$matDataArr = [];
if ($result_mat && $result_mat->num_rows > 0) {
    while($row = $result_mat->fetch_assoc()) {
        $matDataArr[$row['log_date']][$row['material_name']] = $row['total_qty'];
    }
}

$conn->close();
?>

<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Shead & Material Summary</title>
<style>
body { margin:0; font-family:"Segoe UI", sans-serif; background:#ADD8E6; color:#2c3e50; }
.sidebar { width:180px; background-color:#2c3e50; color:#fff; display:flex; flex-direction:column; padding-top:15px; position:fixed; left:0; top:0; bottom:0; box-shadow:2px 0 10px rgba(0,0,0,0.2);}
.sidebar h2 {text-align:center; margin-bottom:20px; font-size:16px; color:#ecf0f1;}
.sidebar a {padding:8px 12px; text-decoration:none; color:#ecf0f1; font-size:13px; transition: all 0.3s;}
.sidebar a:hover {background-color:#34495e; padding-left:20px;}
header { background:#1b263b; color:#fff; display:flex; align-items:center; justify-content:space-between; padding:6px 10px; border-radius:8px; margin:10px 0 15px; font-size:13px; }
header h1 { font-size:15px; margin:0; font-weight:500; }
.filter-group { display:flex; gap:5px; }
.filter-box { background:#fff; border-radius:6px; padding:3px 8px; border:none; font-size:12px; color:#2c3e50; outline:none; cursor:pointer; }
.main-content { margin-left:180px; padding:15px; }
.table-container { overflow-x:auto; background:rgba(255,255,255,0.95); border-radius:10px; box-shadow:0 6px 20px rgba(0,0,0,0.08); padding:12px; margin-bottom:30px; }
table { border-collapse:collapse; width:100%; text-align:center; font-size:11.5px; margin-bottom:20px; }
th { background:#2e86de; color:white; padding:5px; position:sticky; top:0; }
td { padding:4px; border-bottom:1px solid #ecf0f1; }
tr:nth-child(even){ background:#f7f9fc; }
tr:hover{ background:#eaf2ff; }
.date-col { font-weight:bold; background:#dff9fb; color:#1b263b; }
.no-data { text-align:center; padding:15px; font-size:13px; color:#7f8c8d; }
@media (max-width:768px){ .sidebar{ width:100%; position:relative;} .main-content{ margin-left:0;} header{ flex-direction:column; gap:5px;} }
</style>
</head>
<body>
<div class="flex h-screen">
<div class="sidebar">
<h2>Dashboard</h2>
 <a href="http://localhost:8080/php/index.php">🏠 Home</a>
      <a href="http://localhost:8080/php/shead_config.php">⚙️ Configuration</a>
      <a href="http://localhost:8080/php/feed_formula_json_to_web.php">📊 Feed Formula</a>
      <a href="http://localhost:8080/php/report.php">📊 Report</a>
      <a href="https://sunfra.com/">💬 Support</a>
</div>

<div class="main-content">
<header>
<h1>📊 Shead & Material Summary</h1>
<form method="GET" class="filter-group" id="filterForm">
<select name="filter" class="filter-box" id="filterSelect">
<option value="today" <?= $filter=='today'?'selected':'' ?>>Today</option>
<option value="yesterday" <?= $filter=='yesterday'?'selected':'' ?>>Yesterday</option>
<option value="weekly" <?= $filter=='weekly'?'selected':'' ?>>This Week</option>
<option value="monthly" <?= $filter=='monthly'?'selected':'' ?>>This Month</option>
<option value="yearly" <?= $filter=='yearly'?'selected':'' ?>>This Year</option>
<option value="custom" <?= $filter=='custom'?'selected':'' ?>>Custom</option>
</select>

<select name="shead" class="filter-box">
<option value="All" <?= $selectedShead=='All'?'selected':'' ?>>All Sheads</option>
<?php foreach ($sheadNames as $shead): ?>
<option value="<?= htmlspecialchars($shead) ?>" <?= $selectedShead==$shead?'selected':'' ?>>
<?= htmlspecialchars($shead) ?>
</option>
<?php endforeach; ?>
</select>

<input type="date" name="from_date" id="fromDate" class="filter-box" value="<?= $from_date ?? '' ?>" style="display:none;">
<input type="date" name="to_date" id="toDate" class="filter-box" value="<?= $to_date ?? '' ?>" style="display:none;">
</form>
</header>

<div class="table-container">
<h3>Shead Grinding Summary</h3>
<?php if (!empty($sheadDataArr)): ?>
<table>
<thead>
<tr>
<th>Date</th>
<?php foreach ($sheadNames as $shead): ?>
<?php if ($selectedShead=='All' || $selectedShead==$shead): ?>
<th><?= htmlspecialchars($shead) ?></th>
<?php endif; ?>
<?php endforeach; ?>
</tr>
</thead>
<tbody>
<?php foreach ($sheadDataArr as $date => $rows): ?>
<tr>
<td class="date-col"><?= htmlspecialchars($date) ?></td>
<?php foreach ($sheadNames as $shead): ?>
<?php if ($selectedShead=='All' || $selectedShead==$shead): ?>
<td><?= $rows[$shead] ?? '-' ?></td>
<?php endif; ?>
<?php endforeach; ?>
</tr>
<?php endforeach; ?>
</tbody>
</table>
<?php else: ?>
<div class="no-data">No records found for selected period.</div>
<?php endif; ?>
</div>

<div class="table-container">
<h3>Feed Material Consumption</h3>
<?php if (!empty($matDataArr)): ?>
<table>
<thead>
<tr>
<th>Date</th>
<?php foreach($materials as $mat): ?>
<th><?= htmlspecialchars($mat) ?></th>
<?php endforeach; ?>
</tr>
</thead>
<tbody>
<?php foreach($matDataArr as $date => $row): ?>
<tr>
<td class="date-col"><?= htmlspecialchars($date) ?></td>
<?php foreach($materials as $mat): ?>
<td><?= isset($row[$mat]) ? $row[$mat] : '-' ?></td>
<?php endforeach; ?>
</tr>
<?php endforeach; ?>
</tbody>
</table>
<?php else: ?>
<div class="no-data">No material logs found for selected period.</div>
<?php endif; ?>
</div>
</div>
</div>

<script>
document.addEventListener('DOMContentLoaded', () => {
    const filter = document.getElementById('filterSelect');
    const fromDate = document.getElementById('fromDate');
    const toDate = document.getElementById('toDate');
    const form = document.getElementById('filterForm');

    function toggleCustomDates() {
        if(filter.value==='custom'){
            fromDate.style.display='inline-block';
            toDate.style.display='inline-block';
            fromDate.required = true;
            toDate.required = true;
        } else {
            fromDate.style.display='none';
            toDate.style.display='none';
            fromDate.required = false;
            toDate.required = false;
        }
    }

    toggleCustomDates();

    filter.addEventListener('change', () => {
        toggleCustomDates();
        if(filter.value !== 'custom'){
            form.submit(); 
        }
    });

    function submitIfDatesFilled(){
        if(filter.value==='custom' && fromDate.value && toDate.value){
            form.submit(); 
        }
    }

    fromDate.addEventListener('change', submitIfDatesFilled);
    toDate.addEventListener('change', submitIfDatesFilled);
});

</script>
</body>
</html>
