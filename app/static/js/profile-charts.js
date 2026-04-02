function loadCharts(eventData, badgeData, xpData, hoursData) {
  new Chart(document.getElementById("eventLineChart"), {
    type: "line",
    data: {
      labels: eventData.labels,
      datasets: [{
        label: "Events",
        data: eventData.values,
        borderColor: "#6c63ff",
        fill: true,
        tension: 0.4
      }]
    }
  });

  new Chart(document.getElementById("badgePieChart"), {
    type: "pie",
    data: {
      labels: badgeData.labels,
      datasets: [{
        data: badgeData.values,
        backgroundColor: ['#6c63ff', '#ffc107', '#28a745', '#17a2b8', '#dc3545']
      }]
    }
  });

  new Chart(document.getElementById("xpBarChart"), {
    type: "bar",
    data: {
      labels: xpData.labels,
      datasets: [{
        data: xpData.values,
        backgroundColor: "#6c63ff"
      }]
    }
  });

  new Chart(document.getElementById("hoursBarChart"), {
    type: "bar",
    data: {
      labels: hoursData.labels,
      datasets: [{
        data: hoursData.values,
        backgroundColor: "#28a745"
      }]
    }
  });
}

