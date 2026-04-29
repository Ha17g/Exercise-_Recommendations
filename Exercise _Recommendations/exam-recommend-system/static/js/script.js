document.addEventListener('DOMContentLoaded', function() {
    console.log('智能习题推荐系统已加载');
    
    // 自动隐藏Flash消息（如果有）
    setTimeout(function() {
        const alerts = document.querySelectorAll('.alert');
        alerts.forEach(function(alert) {
            alert.style.opacity = '0';
            setTimeout(function() {
                alert.style.display = 'none';
            }, 500);
        });
    }, 3000);
});
