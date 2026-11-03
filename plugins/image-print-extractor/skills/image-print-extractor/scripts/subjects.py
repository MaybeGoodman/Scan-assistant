"""The eight V1.0 modules (R01, section 3) and their per-candidate review checklists (D01).

Textbook defaults are recorded per module; a task may override the range for this run
only (D02). Edition/volume/unit mappings are not encoded here: where the source of a
mapping is not verified, it is reported as unknown rather than guessed.
"""

MODULES = {
    'M01': {'stage': '初中', 'subject': '数学', 'textbook': '华东师大版', 'grades': '初一至初三',
            'checklist': {
                'solution_exists': '解存在且唯一性符合设问（含无解、多解说明）',
                'domain_parameters': '定义域、参数取值与题设一致',
                'geometry_conditions': '几何条件自洽，图形可画，证明链完整',
                'steps_controlled': '计算量和推理步数与原题相当',
                'junior_scope': '只用初中方法即可完成'},
            'typical': ['方程或函数', '几何图', '多小问应用题']},
    'M02': {'stage': '初中', 'subject': '物理', 'textbook': '沪科版', 'grades': '八至九年级',
            'checklist': {
                'model_kept': '物理模型和规律与原题一致',
                'units_checked': '单位、数量级和有效数字核算通过',
                'direction_range': '方向、量程和读数合理',
                'figure_consistent': '电路连接、光路或受力与题干一致',
                'junior_method': '只用初中方法即可完成'},
            'typical': ['力热基础计算', '电路或光路', '实验题']},
    'M03': {'stage': '初中', 'subject': '化学', 'textbook': '沪教版', 'grades': '九年级',
            'checklist': {
                'principle_kept': '反应原理、体系和化学计量模型与原题一致',
                'formula_mass': '式量计算正确',
                'conservation': '元素守恒与质量守恒成立，方程式已配平',
                'conditions_apparatus': '反应条件、试剂和装置合理',
                'junior_scope': '不依赖高中知识'},
            'typical': ['基础方程式', '质量计算', '装置与操作题']},
    'M04': {'stage': '初中', 'subject': '英语', 'textbook': '仁爱版', 'grades': '初一至初三',
            'checklist': {
                'target_language': '目标词汇、语法和语言任务与原题一致',
                'length_vocabulary': '句长、篇幅和词汇在初中范围内',
                'unique_answer': '客观题选项排他，答案唯一',
                'evidence_located': '阅读题答案能在语篇中定位',
                'task_executable': '写作任务要求清楚可执行'},
            'typical': ['语法选择', '完形或阅读共享语篇', '情境写作']},
    'M05': {'stage': '高中', 'subject': '数学', 'textbook': '人教版 A 版', 'grades': '必修与选择性必修',
            'checklist': {
                'core_idea': '核心数学思想与小问梯度与原题一致',
                'domain_parameters': '定义域、参数区间正确',
                'boundary_cases': '边界与退化情形已检查',
                'solution_set': '解集、最值或图像结论经独立重算',
                'geometry_proof': '几何关系或证明经验证（无几何时写 true 并在 notes 说明）'},
            'typical': ['函数或数列', '三角', '解析或立体几何', '概率统计综合']},
    'M06': {'stage': '高中', 'subject': '物理', 'textbook': '鲁科版', 'grades': '必修与选择性必修',
            'checklist': {
                'model_kept': '受力、运动、能量或电磁模型与原题一致',
                'units_signs': '单位、符号和方向核算通过',
                'initial_boundary': '初始和边界条件可实现',
                'chained_quantities': '小问之间物理量传递正确',
                'figure_consistent': '图表条件与题干一致'},
            'typical': ['多阶段计算', '受力或运动图', '电磁和实验数据题']},
    'M07': {'stage': '高中', 'subject': '化学', 'textbook': '苏教版', 'grades': '必修与选择性必修',
            'checklist': {
                'system_kept': '反应体系和综合层级与原题一致',
                'conservation': '元素、电荷、电子守恒成立',
                'equilibrium_electrochem': '平衡、电化学或离子反应判断正确',
                'reagents_apparatus': '试剂和装置合理',
                'inference_chain': '推断链唯一且可完成'},
            'typical': ['离子与氧化还原方程式', '实验装置', '电化学或综合推断']},
    'M08': {'stage': '高中', 'subject': '英语', 'textbook': '北师大版', 'grades': '必修与选择性必修',
            'checklist': {
                'language_natural': '语言自然地道，句法复杂度与原题相当',
                'evidence_sentences': '答案有证据句支撑，推断层级与原题一致',
                'no_ambiguity': '选项无歧义，答案唯一',
                'discourse_ability': '篇章能力目标与原题一致',
                'task_standard': '开放题按任务标准可核验'},
            'typical': ['完形', '推断型阅读', '应用文或相同任务类型的写作']},
}
DIFFICULTIES = ('same', 'easier', 'harder')
DIFFICULTY_LABELS = {'same': '同难度', 'easier': '降低难度', 'harder': '提高难度'}


def module(code):
    if code not in MODULES:
        raise ValueError(f'未知模块 {code}；可用 M01–M08')
    return MODULES[code]


def describe(code):
    info = module(code)
    return f'{code} {info["stage"]}{info["subject"]}（{info["textbook"]}）'
