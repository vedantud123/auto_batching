<?php
date_default_timezone_set('Asia/Kolkata');

$host = "localhost"; 
$user = "root";     
$pass = "sunfra";   
$db   = "auto_batching"; 

$conn = new mysqli($host, $user, $pass, $db);
if ($conn->connect_error) {
    die("Connection failed: " . $conn->connect_error);
}

$mac_address = trim(shell_exec("cat /sys/class/net/wlan0/address")); 
$mac_address_formatted = str_replace(":", "-", $mac_address);

$api_url = "https://sunfra.com/farm/csv/feed_formula_json.php?mac_address=" . $mac_address_formatted;
$response = file_get_contents($api_url);
if ($response === FALSE) {
    die("Failed to fetch API data for feed formula.");
}
$data = json_decode($response, true);
if ($data === NULL) {
    die("Failed to decode JSON (feed formula).");
}

$conn->query("DELETE FROM feed_formula_detail");
$stmt = $conn->prepare("INSERT INTO feed_formula_detail 
    (id, feed_formulaType, quantity, feed_rawMaterial_name, type, client_id) 
    VALUES (?, ?, ?, ?, ?, ?)");
foreach ($data as $row) {
    $stmt->bind_param(
        "issssi",
        $row['id'],
        $row['feed_formulaType'],
        $row['quantity'],
        $row['feed_rawMaterial_name'],
        $row['type'],
        $row['client_id']
    );
    $stmt->execute();
}
$stmt->close();
echo "Feed formula updated successfully.<br>";

$api_url = "https://sunfra.com/farm/csv/shead_chick_grower_json.php?mac_address=" . $mac_address_formatted;
$response = file_get_contents($api_url);
if ($response === FALSE) {
    die("Failed to fetch API data for shead config.");
}
$data = json_decode($response, true);
if ($data === NULL) {
    die("Failed to decode JSON (shead config).");
}

$conn->query("DELETE FROM shead_config");
$stmt = $conn->prepare("INSERT INTO shead_config (id, shead_name, description, client_id) VALUES (?, ?, ?, ?)");
foreach ($data as $row) {
    $stmt->bind_param(
        "issi",
        $row['id'],
        $row['shead_name'],
        $row['description'],
        $row['client_id']
    );
    $stmt->execute();
}
$stmt->close();
echo "Shead configuration updated successfully.<br>";

$apiUrl = "https://sunfra.com/farm/csv/feed_raw_material_json.php?mac_address=" . $mac_address_formatted;
$response = file_get_contents($apiUrl);
if ($response === FALSE) {
    die("Error fetching API data (raw materials).");
}
$data = json_decode($response, true);
if (isset($data["material"])) {
    $conn->query("DELETE FROM feed_rawmaterial");
    foreach ($data["material"] as $material) {
        $name = $conn->real_escape_string($material["name"]);
        $stock = (float)$material["stock"];
        $metrics = $conn->real_escape_string($material["metric"]);
        $type = $conn->real_escape_string($material["type"]);
        $client_id = (int)$material["client_id"];

        $sql = "INSERT INTO feed_rawmaterial (name, stock, metrics, type, client_id) 
                VALUES ('$name', '$stock', '$metrics', '$type', '$client_id')";
        $conn->query($sql);
    }
    echo "Feed raw materials updated successfully.<br>";
} else {
    echo "No materials found in API response.<br>";
}

$query = "
    SELECT 
        DATE(`date`) AS log_date,
        shead_name, 
        COUNT(*) AS running_count
    FROM 
        batching_running_logs
    WHERE 
        STATUS = 'Running'
    GROUP BY 
        log_date, 
        shead_name
    ORDER BY 
        shead_name, log_date;
";
$result = $conn->query($query);

if ($result && $result->num_rows > 0) {
    echo "<br>Sending running logs to API...<br>";

    while ($row = $result->fetch_assoc()) {
        $shead_name = trim($row['shead_name']);
        $log_date   = $row['log_date'];
        $count      = (float)$row['running_count'];

        if (empty($shead_name)) {
            echo "❌ Skipping empty Shead name for date: {$log_date}<br>";
            continue;
        }

        $apiUrl = "https://sunfra.com/farm/sunfra_clients/csv/feed_feeding_to_shead_through_auto_batching.php";
        $apiUrl .= "?sheadNo=" . urlencode($shead_name);
        $apiUrl .= "&tons=" . urlencode($count);
        $apiUrl .= "&mac_address=" . urlencode($mac_address_formatted);

        $response = @file_get_contents($apiUrl);

        if ($response === FALSE) {
            echo "❌ Failed to reach API for Shead: {$shead_name} ({$log_date})<br>";
            continue;
        }

        $responseData = json_decode($response, true);

        if (isset($responseData['status']) && $responseData['status'] === 'ok') {
            echo "✅ Sent successfully for Shead: {$shead_name} ({$log_date})<br>";
            $update = $conn->prepare("
                UPDATE batching_running_logs 
                SET STATUS = 'Done'
                WHERE shead_name = ? AND DATE(`date`) = ?
            ");
            $update->bind_param("ss", $shead_name, $log_date);
            $update->execute();
            $update->close();
        } else {
            echo "❌ Failed to send data for Shead: {$shead_name} ({$log_date})<br>";
            echo "Response: {$response}<br>";
        }
    }
} else {
    echo "<br>No Running logs found.<br>";
}

echo "<br>All operations completed successfully.<br>";
?>
