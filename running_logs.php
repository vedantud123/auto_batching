<?php
error_reporting(E_ALL);
ini_set('display_errors', 1);

header('Content-Type: application/json');
date_default_timezone_set('Asia/Kolkata');
$current_datetime = date("Y-m-d H:i:s");

$host = "localhost";
$user = "root";
$pass = "sunfra";
$db   = "auto_batching";

$conn = new mysqli($host, $user, $pass, $db);
if ($conn->connect_error) {
    die(json_encode(["status" => "error", "message" => "Database connection failed: " . $conn->connect_error]));
}

$shead_name = isset($_REQUEST['shead_name']) ? trim($_REQUEST['shead_name']) : '';
$ton = isset($_REQUEST['ton']) ? trim($_REQUEST['ton']) : '';
$client_id = isset($_REQUEST['client_id']) ? trim($_REQUEST['client_id']) : '';

if (empty($shead_name) || empty($ton) || empty($client_id)) {
    echo json_encode(["status" => "error", "message" => "Missing required fields."]);
    exit;
}

$response = [];

$stmt = $conn->prepare("INSERT INTO batching_running_logs (shead_name, ton, client_id, date, status) VALUES (?, ?, ?, ?, ?)");
$default_status = 'running';
$stmt->bind_param("siiss", $shead_name, $ton, $client_id, $current_datetime, $default_status);

if ($stmt->execute()) {
    $response['insertion'] = "Data inserted successfully.";
} else {
    $response['insertion'] = "Failed to insert data: " . $stmt->error;
}
$stmt->close();

$converted_shead = strtolower(str_replace(' ', '_', $shead_name));

$select_stmt = $conn->prepare("SELECT feed_rawMaterial_name, quantity FROM feed_formula_detail WHERE feed_formulaType = ?");
$select_stmt->bind_param("s", $converted_shead);
$select_stmt->execute();
$result = $select_stmt->get_result();

$stock_messages = [];
if ($result->num_rows > 0) {
    while ($row = $result->fetch_assoc()) {
        $material_name = $row['feed_rawMaterial_name'];
        $quantity_used = (float)$row['quantity'];

        $update_stmt = $conn->prepare("UPDATE feed_rawmaterial SET stock = stock - ? WHERE name = ?");
        $update_stmt->bind_param("ds", $quantity_used, $material_name);

        if ($update_stmt->execute()) {
            $stock_messages[] = "$material_name stock reduced by $quantity_used";

            $insert_stmt = $conn->prepare("INSERT INTO feed_material_reduction_logs (material_name, reduced_quantity, timestamp, client_id) VALUES (?, ?, NOW(), ?)");
            
            $insert_stmt->bind_param("sdi", $material_name, $quantity_used, $client_id);

            if (!$insert_stmt->execute()) {
                $stock_messages[] = "Failed to log $material_name reduction: " . $insert_stmt->error;
            }

            $insert_stmt->close();
        } else {
            $stock_messages[] = "Failed to update $material_name: " . $update_stmt->error;
        }
        $update_stmt->close();
    }
} else {
    $stock_messages[] = "⚠️ No feed formula found for '$converted_shead'.";
}

$select_stmt->close();
$conn->close();

$response['stock_update'] = $stock_messages;
echo json_encode($response, JSON_PRETTY_PRINT);
?>

