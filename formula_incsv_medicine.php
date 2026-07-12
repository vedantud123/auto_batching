<?php
error_reporting(E_ALL);
ini_set('display_errors', 1);

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

$host = "localhost";
$user = "root";
$pass = "sunfra";
$db   = "auto_batching";

$conn = new mysqli($host, $user, $pass, $db);
if ($conn->connect_error) {
    die("Database connection failed: " . $conn->connect_error);
}

$sumParts = [];
foreach ($formatted as $col) {
    $sumParts[] = "SUM(CASE WHEN feed_formulaType = '$col' THEN quantity ELSE 0 END) AS `$col`";
}

$sumColumns = implode(",\n        ", $sumParts);

$query = "
    SELECT 
        feed_rawMaterial_name AS Material,
        $sumColumns
    FROM 
        feed_formula_detail
    WHERE 
        type = 'Feed_Medicine'
    GROUP BY 
        feed_rawMaterial_name
    ORDER BY 
        FIELD(feed_rawMaterial_name, 'Maize', 'B.rice', 'DORB', 'StoneGrit', 'Soya', 'Rapeseed', 'DDGS', 'Stone Powder')
";

$result = $conn->query($query);

if (!$result) {
    die("Query failed: " . $conn->error);
}

$headers = array_merge(['Material'], $formatted);
echo implode(',', $headers) . "\n";

while ($row = $result->fetch_assoc()) {
    $values = [$row['Material']];
    foreach ($formatted as $col) {
        $quantity = isset($row[$col]) ? $row[$col] : 0;
        $quantity_in_grams = $quantity * 1000; 
        $values[] = $quantity_in_grams;
    }
    echo implode(',', $values) . "\n";
}


$conn->close();
?>

