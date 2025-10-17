import json
import re

class MotorThresholdChecker:
    """
    电机阈值检查器
    功能：根据Velocity值通过拟合方程计算PWM值，并与阈值比较返回布尔结果
    """
    
    def __init__(self, fit_equations_path, pwm_thresholds_path):
        """
        初始化电机阈值检查器
        
        参数:
        fit_equations_path (str): 拟合方程JSON文件路径
        pwm_thresholds_path (str): PWM阈值JSON文件路径
        """
        # 加载拟合方程JSON文件
        with open(fit_equations_path, 'r', encoding='utf-8') as f:
            self.fit_equations = json.load(f)
        
        # 加载PWM阈值JSON文件
        with open(pwm_thresholds_path, 'r', encoding='utf-8') as f:
            self.pwm_thresholds = json.load(f)
        
        # 解析所有拟合方程，提取系数
        self.motor_coefficients = {}
        for motor_name, equation in self.fit_equations.items():
            coefficients = self._parse_equation(equation)
            if coefficients:
                self.motor_coefficients[motor_name] = coefficients
            else:
                print(f"警告: 无法解析电机 {motor_name} 的方程")
    
    def _parse_equation(self, equation_str):
        """
        解析拟合方程字符串，提取二次项、一次项和常数项系数
        
        参数:
        equation_str (str): 拟合方程字符串
        
        返回:
        tuple: (a, b, c) 其中a为二次项系数，b为一次项系数，c为常数项
        """
        # 使用正则表达式提取所有数值（包括正负号和小数点）
        numbers = re.findall(r"[-+]?\d*\.\d+|\d+", equation_str)
        
        if len(numbers) >= 3:
            try:
                a = float(numbers[0])  # 二次项系数
                b = float(numbers[1])  # 一次项系数
                c = float(numbers[2])  # 常数项
                return (a, b, c)
            except ValueError:
                return None
        return None
    
    def calculate_pwm(self, velocity, motor_name):
        """
        根据速度值计算指定电机的PWM值
        
        参数:
        velocity (float): 速度值
        motor_name (str): 电机名称（如 "motor_3"）
        
        返回:
        float: 计算出的PWM值，如果电机不存在返回None
        """
        if motor_name not in self.motor_coefficients:
            return None
        
        a, b, c = self.motor_coefficients[motor_name]
        pwm_value = a * (velocity ** 2) + b * velocity + c
        return pwm_value
    
    def check_threshold(self, velocity, motor_name, tolerance=10):
        """
        检查单个电机的PWM值是否超过阈值（考虑误差范围）
        
        参数:
        velocity (float): 速度值
        motor_name (str): 电机名称
        tolerance (float): PWM误差容忍范围，默认10
        
        返回:
        bool: True表示超过阈值（含误差范围），False表示未超过阈值
        """
        # 计算PWM值
        pwm_value = self.calculate_pwm(velocity, motor_name)
        if pwm_value is None:
            print(f"警告: 无法计算电机 {motor_name} 的PWM值")
            return False
        
        # 获取阈值
        if motor_name not in self.pwm_thresholds:
            print(f"警告: 电机 {motor_name} 的阈值不存在")
            return False
        
        threshold = self.pwm_thresholds[motor_name]
        
        # 计算误差范围
        lower_bound = threshold - tolerance
        upper_bound = threshold + tolerance
        
        # 判断是否在误差范围内
        in_tolerance_range = lower_bound <= pwm_value <= upper_bound
        exceeds_threshold = pwm_value >= threshold
        
        # 最终结果：超过阈值或在误差范围内都算作"超过"
        result = exceeds_threshold or in_tolerance_range
        
        # 打印详细信息
        print(f"电机: {motor_name}")
        print(f"  速度值: {velocity}")
        print(f"  计算PWM值: {pwm_value:.4f}")
        print(f"  阈值PWM值: {threshold}")
        print(f"  误差范围: [{lower_bound:.4f}, {upper_bound:.4f}] (容忍度: ±{tolerance})")
        if in_tolerance_range and not exceeds_threshold:
            print(f"  比较结果: 在误差范围内 (PWM={pwm_value:.4f} 在 [{lower_bound:.4f}, {upper_bound:.4f}] 内)")
        else:
            print(f"  比较结果: {'超过阈值' if exceeds_threshold else '未超过阈值'}")
        print("-" * 40)
        
        return result
    
    def check_all_motors(self, velocity, tolerance=10):
        """
        检查所有电机的PWM值是否超过各自阈值（考虑误差范围）
        
        参数:
        velocity (float): 速度值
        tolerance (float): PWM误差容忍范围，默认10
        
        返回:
        dict: 电机名称到布尔值的映射
        """
        results = {}
        for motor_name in self.fit_equations.keys():
            results[motor_name] = self.check_threshold(velocity, motor_name, tolerance)
        return results

# 使用示例
if __name__ == "__main__":
    # 初始化检查器（请替换为实际文件路径）
    checker = MotorThresholdChecker(
        fit_equations_path="quadratic_fit_formulas.json",
        pwm_thresholds_path="inflection_pwm_values.json"
    )
    
    # 测试速度值
    test_velocity = 100.0
    
    # 检查所有电机
    results = checker.check_all_motors(test_velocity)
    
    # 打印最终结果
    print("\n最终结果汇总:")
    print(f"速度值: {test_velocity}")
    for motor_name, exceeds_threshold in results.items():
        status = "超过阈值" if exceeds_threshold else "未超过阈值"
        print(f"{motor_name}: {status}")
    
    # 也可以单独检查特定电机
    # motor_3_result = checker.check_threshold(test_velocity, "motor_3")
    # print(f"motor_3 结果: {motor_3_result}")