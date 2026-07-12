<?php
error_reporting(E_ALL);
ini_set('display_errors', 1);

$host = "localhost";
$user = "root";
$pass = "sunfra";
$db   = "auto_batching";

$conn = new mysqli($host, $user, $pass, $db);
if ($conn->connect_error) {
    die(json_encode([
        "status" => "error",
        "message" => "Database connection failed: " . $conn->connect_error
    ]));
}

$sql = "SELECT id, motor_number, material_name, client_id, number_of_motor FROM motor_config LIMIT 1";
$result = $conn->query($sql);

if ($result && $result->num_rows > 0) {
    $data = [];
    while ($row = $result->fetch_assoc()) {
        $data[] = [
            "id" => $row["id"],
            "motor_number" => $row["motor_number"],
            "material_name" => $row["material_name"],
            "client_id" => $row["client_id"],
            "number_of_motor" => $row["number_of_motor"]
        ];
    }

    echo json_encode([
        "status" => "success",
        "data" => $data
    ], JSON_PRETTY_PRINT);
} else {
    echo json_encode([
        "status" => "error",
        "message" => "No data found in motor_config table."
    ]);
}

$conn->close();
?>

