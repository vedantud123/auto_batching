<?php
header('Content-Type: application/json');

$response = [];

$client_id = 1; 

$host = "localhost"; 
$user = "root";     
$pass = "sunfra";   
$db   = "auto_batching"; 

$mysqli = new mysqli($host, $user, $pass, $db);

if ($mysqli->connect_error) {
    echo json_encode(['status' => 'error', 'message' => 'Database connection failed: ' . $mysqli->connect_error]);
    exit;
}

$material_day_logs = "
    SELECT material_name, SUM(reduced_quantity) AS total_reduction
    FROM `feed_material_reduction_logs`
    WHERE `timestamp` BETWEEN DATE_SUB(NOW(), INTERVAL 7 DAY) AND NOW()
      AND `client_id` = $client_id
    GROUP BY material_name
";

$material_day_logs_result = $mysqli->query($material_day_logs);

if ($material_day_logs_result) {
    while ($row = $material_day_logs_result->fetch_assoc()) {
        $material_name = $mysqli->real_escape_string($row["material_name"]);
        $total_reduction = floatval($row["total_reduction"]);
        $reduction_quantity_avg = ($total_reduction > 0) ? ($total_reduction / 7) : 1;

        $update_day = "
            UPDATE `feed_rawmaterial`
            SET `days` = `stock` / $reduction_quantity_avg
            WHERE `name` = '$material_name' AND `client_id` = $client_id
        ";
        $mysqli->query($update_day);
    }
    $material_day_logs_result->free();
}

$query = "
    SELECT * 
    FROM feed_rawmaterial
    WHERE client_id = $client_id
      AND type IN ('Feed Medicine', 'Feed_Formula', 'Water Medicine')
    ORDER BY type ASC
";

$materials_by_client = [];

if ($result = $mysqli->query($query)) {
    while ($row = $result->fetch_assoc()) {
        $materials_by_client[] = [
            'id' => $row["id"],
            'name' => $row["name"],
            'stock' => floatval($row["stock"]),
            'metric' => $row["metric"],
            'type' => $row["type"],
            'days' => round(floatval($row["days"]), 2)
        ];
    }
    $result->free();
} else {
    echo json_encode(['status' => 'error', 'message' => 'Error fetching raw material data: ' . $mysqli->error]);
    exit;
}

$mysqli->close();

$response = [
    $client_id => $materials_by_client
];

echo json_encode($response, JSON_PRETTY_PRINT);
?>
