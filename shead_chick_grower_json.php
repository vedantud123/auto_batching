<?php
header('Content-Type: application/json');

$client_id = 1;

$host = "localhost"; 
$user = "root";     
$pass = "sunfra";   
$db   = "auto_batching"; 

$mysqli = new mysqli($host, $user, $pass, $db);

if ($mysqli->connect_error) {
    http_response_code(500);
    echo json_encode(['error' => 'Database connection failed']);
    exit;
}

$query = "
    SELECT shead_name 
    FROM shead_config 
    WHERE client_id = $client_id 
    ORDER BY id ASC
";

$result = $mysqli->query($query);

$data = [];

if ($result && $result->num_rows > 0) {
    while ($row = $result->fetch_assoc()) {
        $data[] = $row;
    }
    echo json_encode($data);
} else {
    echo json_encode(['message' => "No records found for client_id = $client_id with description = 'Shead Number'"]);
}

$mysqli->close();
?>
