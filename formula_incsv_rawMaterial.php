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

$url = "http://localhost:8080/php/shead_chick_grower_json.php?client_id=1";
$response = file_get_contents($url);
$data = json_decode($response, true);

$formatted = [];
if (!empty($data)) {
    foreach ($data as $item) {
        if (isset($item['shead_name'])) {
            $name = strtolower(str_replace(' ', '_', $item['shead_name']));
            $formatted[] = $name;
        }
    }
}

if (empty($formatted)) {
    die("No shead/chick/grower data found from API.");
}

$sql = "SELECT material_name FROM motor_config ORDER BY motor_number ASC";
$result = $conn->query($sql);

$motorOrder = [];
if ($result && $result->num_rows > 0) {
    while ($row = $result->fetch_assoc()) {
        $motorOrder[] = $row['material_name'];
    }
}

if (empty($motorOrder)) {
    die("No motor configuration found.");
}

$sumParts = [];
foreach ($formatted as $col) {
    $sumParts[] = "SUM(CASE WHEN feed_formulaType = '$col' THEN quantity ELSE 0 END) AS `$col`";
}
$sumColumns = implode(",\n        ", $sumParts);

$orderByField = "'" . implode("','", $motorOrder) . "'";
$whereField   = "'" . implode("','", $motorOrder) . "'";

$query = "
    SELECT 
        feed_rawMaterial_name AS Material,
        $sumColumns
    FROM 
        feed_formula_detail
    WHERE 
        type = 'Feed_Formula'
        AND feed_rawMaterial_name IN ($whereField)
    GROUP BY 
        feed_rawMaterial_name
    ORDER BY 
        FIELD(feed_rawMaterial_name, $orderByField)
";

$result = $conn->query($query);

if (!$result) {
    die('Query failed: ' . $conn->error);
}

$headers = array_merge(['Material'], $formatted);
echo implode(',', $headers) . "\n";

while ($row = $result->fetch_assoc()) {
    $values = [$row['Material']];
    foreach ($formatted as $col) {
        $values[] = isset($row[$col]) ? (int)$row[$col] : 0;
    }
    echo implode(',', $values) . "\n";
}

$conn->close();
?>
